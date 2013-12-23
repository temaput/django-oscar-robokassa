# set encoding=utf-8

from logging import getLogger
log = getLogger(__name__)

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

PaymentDetailsView = get_class('checkout.views', 
        'PaymentDetailsView')
CheckoutSessionData = get_class('checkout.utils', 'CheckoutSessionData')
Basket = get_model('basket', 'Basket')
Selector = get_class('partner.strategy', 'Selector')

selector = Selector()


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
        return self.robokassa_extra_params.get('order_num', None)

    @property
    def session_key(self):
        return self.robokassa_extra_params.get('session_key', None)

class SuccessResponseView(PaymentDetailsView, ProcessData):
    """ Landing page for succesfull redirects from ROBOKASSA
    Should check the parameters and if OK render the thankyou page
    """
    form = SuccessRedirectForm

    def dispatch(self, request, *args, **kwargs):
        self.checkout_session = CheckoutSessionData(request)
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
            self.basket = Basket.objects.get(id=self.basket_num,
                                        status=Basket.FROZEN)
        except Basket.DoesNotExist:
            messages.error(
                self.request,
                u"Данному платежу не соответствует ни одна корзина")
            return HttpResponseRedirect(reverse('basket:summary'))
        strategy = selector.strategy(
            request=request, user=request.user)
        self.basket.strategy = strategy

        # keep this for legacy
        success_page_visited.send(sender = self, 
                InvId = self.basket_num, OutSum = self.robokassa_amount,
                             extra = self.robokassa_extra_params)
        # if everything OK finish order placement
        submission = self.build_submission(basket=self.basket)
        return self.submit(**submission)

    def generate_order_number(self, basket):
        """ we already have an order_number, just return it """
        return self.order_num if self.order_num else \
                super(SuccessResponseView, self).generate_order_number(basket)

    def handle_payment(self, order_number, total_incl_tax, **kwargs):
        """
        finalize robokassa payment
        """

        amount_allocated = self.robokassa_amount
        # Record payment source and event
        source_type, is_created = SourceType.objects.get_or_create(
                name=u'Робокасса', code='robokassa')
        source = Source(source_type=source_type, 
                amount_allocated=amount_allocated)
        if STRICT_CHECK:
            source.amount_debited=amount_allocated
        self.add_payment_source(source)
        self.add_payment_event('allocated', amount_allocated)
        if STRICT_CHECK:
            self.add_payment_event('settled', amount_allocated)


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
                             extra = self.robokassa_extra_params)

        return HttpResponse('OK%s' % self.basket_num)
