# set encoding=utf-8

from logging import getLogger
log = getLogger('robokassa.view')

from django.views.generic import RedirectView, View
from django.shortcuts import get_object_or_404
from django.db.models import get_model
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound
from django.contrib import messages
from oscar.core.loading import get_class
from oscar.apps.payment.models import SourceType, Source
from robokassa.conf import USE_POST, STRICT_CHECK
from robokassa.models import SuccessNotification
from robokassa.forms import ResultURLForm, SuccessRedirectForm, FailRedirectForm
from robokassa.signals import result_received, success_page_visited, fail_page_visited

ThankYouView = get_class('checkout.views', 'ThankYouView')
Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
OrderNumberGenerator = get_class('order.utils', 'OrderNumberGenerator')

class ProcessData(object):
    def get_data(self, request):
        if request.method == 'GET' and not USE_POST:
                return request.GET
        elif request.method == 'POST' and USE_POST:
                return request.POST

    def process_data(self, data):
        """ here is where all the checking occurs """
        self.robokassa_cleaned_data = None
        self.robokassa_extra_params = {}
        form = self.form(data)
        if form.is_valid():
            self.robokassa_cleaned_data = form.cleaned_data
            self.robokassa_extra_params = form.extra_params()
        else:
            log.error("Error checking data: %s", form.errors)

    @property
    def basket_num(self): 
        return self.robokassa_cleaned_data.get('InvId')

    @property
    def robokassa_amount(self):
        return self.robokassa_cleaned_data.get('OutSum')

    @property
    def order_num(self):
        order_num = self.robokassa_extra_params.get('order_num', None)
        if order_num is None:
            log.warning("order number was not restored, using default")
            order_num = OrderNumberGenerator.order_number(self.basket)
        return order_num

    @property
    def session_key(self):
        return self.robokassa_extra_params.get('session_key', None)

class SuccessResponseView(ThankYouView, ProcessData):
    """ Landing page for succesfull redirects from ROBOKASSA
    Should check the parameters and if OK render the thankyou page
    """
    form = SuccessRedirectForm

    def dispatch(self, request, *args, **kwargs):
        data = self.get_data(request)
        if data is None:
            return self.http_method_not_allowed(request, *args, **kwargs)
        self.process_data(data)
        if self.robokassa_cleaned_data is None:
            messages.error(
                self.request,
                (u"Возникли ошибки при обработке Вашего платежа, пожалуйста, "
                u"свяжитесь с нами по телефону"))
            log.error("SuccessRedirect error: bad data")
            return HttpResponseRedirect(reverse('basket:summary'))

        # lets find the basket
        try:
            self.basket = Basket.objects.get(id=self.basket_num)
        except Basket.DoesNotExist:
            messages.error(
                self.request,
                u"Данному платежу не соответствует ни одна корзина")
            return HttpResponseRedirect(reverse('basket:summary'))

        # keep this for legacy
        success_page_visited.send(sender = self, 
                InvId = self.basket_num, OutSum = self.robokassa_amount,
                             extra = self.robokassa_extra_params)
        # if everything OK render thank-you page

        return super(SuccessResponseView, self).get(request, *args, **kwargs)

    def get_object(self):
        log.debug("looking for order # %s", self.order_num)
        return get_object_or_404(Order, number=self.order_num)



class FailResponseView(RedirectView, ProcessData):
    permanent = False
    form = FailRedirectForm

    def dispatch(self, request, *args, **kwargs):
        data = self.get_data(request)
        if data is None:
            return self.http_method_not_allowed(request, *args, **kwargs)
        self.process_data(data)
        if self.robokassa_cleaned_data is None:
            return HttpResponseNotFound
        basket = get_object_or_404(Basket, id=self.basket_num,
                            status=Basket.FROZEN)
        basket.thaw()

        # keep this for legacy
        fail_page_visited.send(sender = basket, 
                InvId = self.basket_num, OutSum = self.robokassa_amount,
                             extra = self.robokassa_extra_params)

        return super(FailResponseView, self).dispatch(request, 
                *args, **kwargs)

    def get_redirect_url(self, **kwargs):
        messages.error(self.request, u"Платеж через Робокассу отменен")
        return reverse('basket:summary')


class ResultResponseView(View, ProcessData):
    form = ResultURLForm

    def dispatch(self, request, *args, **kwargs):
        log.debug("="*80)
        log.debug("In result view")
        log.debug("="*80)
        data = self.get_data(request)
        log.debug("data is %s", data)
        if data is None:
            return self.http_method_not_allowed(request, *args, **kwargs)
        self.process_data(data)
        log.debug("cleaned data is %s", self.robokassa_cleaned_data)
        if self.robokassa_cleaned_data is None:
            return HttpResponse('error: bad signature')
        log.debug("basket num is %s", self.basket_num)
        self.basket = get_object_or_404(Basket, id=self.basket_num,
                                status=Basket.FROZEN)

        # checking complete: create notification and send confirmation
        SuccessNotification.objects.create(
                InvId = self.basket_num, OutSum = self.robokassa_amount)
        # keeping this for legacy
        result_received.send(sender = self.basket, 
                InvId = self.basket_num, OutSum = self.robokassa_amount,
                order_num = self.order_num, session_key = self.session_key,
                             extra = self.robokassa_extra_params)

        return HttpResponse('OK%s' % self.basket_num)
