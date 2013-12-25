# set encoding=utf-8

from logging import getLogger
log = getLogger('robokassa.receivers')

from django.http import HttpRequest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth.models import AnonymousUser

from oscar.apps.checkout.mixins import OrderPlacementMixin
from oscar.apps.checkout.utils import CheckoutSessionData
from oscar.apps.payment.models import SourceType, Source
from oscar.core.loading import get_class
from oscar.core import prices

from robokassa.signals import result_received, success_page_visited, fail_page_visited

Selector = get_class('partner.strategy', 'Selector')
post_payment = get_class('checkout.signals', 'post_payment')

selector = Selector()

class RobokassaOrderPlacement(OrderPlacementMixin):

    def handle_successful_order(self, order):
        log.info("Order with number %s, succesfully placed", order.number)
        if not hasattr(self, 'checkout_session'):  # this is a worst case scenario
            self.view_signal.send(sender=self, order=order, user=order.user,
                    confirmation_not_sent=True)
        else:
            super(RobokassaOrderPlacement, self).handle_successful_order(order)


def place_order(sender, **kwargs):
    """ collect basket, user, shipping_method and address, order_number, total
    and pass them to handle_order_placement, but first add payment events and
    sources """
    request = kwargs.get('request', None) or HttpRequest()
    basket = sender
    user = basket.owner if basket.owner else AnonymousUser()
    guest_email = None

    strategy = selector.strategy(user=user)
    session_data = shipping_address = shipping_method = None
    log.debug("initialising: \n basket = %s \n usr = %s \n strategy = %s",
            basket, user, strategy)
    basket.strategy = strategy
    amount_allocated = kwargs['OutSum']
    session_key  = kwargs['session_key']
    order_num =    kwargs['order_num']
    if session_key is not None:
        session = SessionStore(session_key = session_key)
        if len(session.items()):
            log.debug("Session %s successfully restored", session)
            request.session = session
            request.user = user
            session_data = CheckoutSessionData(request)
            if isinstance(user, AnonymousUser):
                guest_email = session_data.get_guest_email()

    order_placement = RobokassaOrderPlacement()
    order_placement.request = request
    if session_data is not None:
        order_placement.checkout_session = session_data
        shipping_address = order_placement.get_shipping_address(basket)
        shipping_method = order_placement.get_shipping_method(
                basket, shipping_address)
        total = order_placement.get_order_totals(basket, shipping_method)
    else:  # session not found, lets try to place order anyway
        log.error(("Session was not restored, trying default order for "
                    "basket #%s"), basket.id)
        basket.is_shipping_required = False
        total = prices.Price(
            currency=basket.currency,
            excl_tax=basket.total_excl_tax, incl_tax=basket.total_incl_tax)

    # now create payment source and events
    source_type, is_created = SourceType.objects.get_or_create(
                name=u'Робокасса', code='robokassa')
    source = Source(source_type=source_type, amount_allocated=amount_allocated,
                amount_debited=amount_allocated)
    order_placement.add_payment_source(source)
    order_placement.add_payment_event('allocated', amount_allocated)
    order_placement.add_payment_event('debited', amount_allocated)
    post_payment.send(sender=order_placement, user=user, source=source)

    # all done lets place an order
    order_placement.handle_order_placement(
                order_num, user, basket, shipping_address, shipping_method,
                total, guest_email=guest_email)
