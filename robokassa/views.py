# set encoding=utf-8

from logging import getLogger
log = getLogger('robokassa.view')

from django.views.generic import RedirectView, View, FormView
from django.shortcuts import get_object_or_404
from django.db.models import get_model
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound
from django.contrib import messages
from oscar.core.loading import get_class
from robokassa.conf import USE_POST, ROBOKASSA_SESSION_KEY, FORM_TARGET
from robokassa.models import SuccessNotification
from robokassa.forms import ResultURLForm, SuccessRedirectForm, FailRedirectForm
from robokassa.signals import result_received, success_page_visited, fail_page_visited
from robokassa.forms import RobokassaForm
from django.views.generic import TemplateView
import time
from datetime import datetime, timedelta

ThankYouView = get_class('checkout.views', 'ThankYouView')
Basket = get_model('basket', 'Basket')
Order = get_model('order', 'Order')
OrderNumberGenerator = get_class('order.utils', 'OrderNumberGenerator')
CheckoutSessionMixin = get_class('checkout.session', 'CheckoutSessionMixin')
PaymentError = get_class('payment.exceptions', 'PaymentError')

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
        result_received.send(sender = self.basket, request=request,
                InvId = self.basket_num, OutSum = self.robokassa_amount,
                order_num = self.order_num, session_key = self.session_key,
                             extra = self.robokassa_extra_params)

        return HttpResponse('OK%s' % self.basket_num)


class RedirectView(CheckoutSessionMixin, FormView):
    """
    Сюда перенаправляются пользователи, разместившие заказ и выбравшие
    оплату через Робокассу. Наша задача:
    - Собрать данные для платежа
    - Сформировать скрытую форму с автосабмитом
    - Перенаправить пользователя на страницу оплаты
    """
    template_name = 'robokassa_redirect.html'
    form_class = RobokassaForm

    def get_redirect_url(self): 
        return FORM_TARGET

    def get_context_data(self, **kwargs):
        ctx = super(RedirectView, self).get_context_data(**kwargs)
        ctx['form_action'] = self.get_redirect_url()
        return ctx

    def get_initial(self):
        session = self.request.session
        if not ROBOKASSA_SESSION_KEY in session:
            log.error("Robokassa session key not found")
            raise PaymentError("Robokassa session key not found")
        initial = session.pop(ROBOKASSA_SESSION_KEY)
        # session.save() # TODO: is this needed?
        session_key = session.session_key
        if session_key is not None:
            initial['session_key'] = session_key
        else:
            log.error('session_key is empty')
        return initial






class SuccessResponseView(TemplateView, ProcessData):
    """ Landing page for succesfull redirects from ROBOKASSA
    Should check the parameters and if OK render the thankyou page
    """
    form = SuccessRedirectForm
    template_name = 'robokassa_success_load.html'

    def dispatch(self, request, *args, **kwargs):
        data = self.get_data(request)
        if data is None:
            return self.http_method_not_allowed(request, *args, **kwargs)
        self.data = data
        self.process_data(data)
        original_request_timestamp = self.request.session.setdefault('original_request_timestamp', int(time.time()))
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

        # first check that order was created
        try:
            self.order = Order.objects.get(number=self.order_num)
            request.session['checkout_order_id'] = self.order.pk
            return HttpResponseRedirect(reverse('checkout:thank-you'))
        except Order.DoesNotExist:
            if datetime.now() - datetime.fromtimestamp(original_request_timestamp) > timedelta(minutes=1):
                messages.error(
                    self.request,
                    u"Время ожидания подтверждения платежа истекло, cвяжитесь с нами по телефону")
                return HttpResponseRedirect(reverse('basket:summary'))
            use_partial = self.data.get('use_partial', False)
            if use_partial:
                return HttpResponse('Expecting payment confirmation', content_type='text/plain', status=200)

        return super(SuccessResponseView, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(SuccessResponseView, self).get_context_data(**kwargs)
        context['form'] = self.form(initial=self.data)
        context['use_post'] = USE_POST
        return context
