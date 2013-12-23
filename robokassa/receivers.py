from django.http import HttpRequest
from django.contrib.sessions.backends.db import SessionStore
from oscar.apps.checkout.mixins import OrderPlacementMixin
from oscar.apps.checkout.utils import CheckoutSessionData
from oscar.apps.payment.models import SourceType, Source
from oscar.core.loading import get_class

Selector = get_class('partner.strategy', 'Selector')

selector = Selector()

class RobokassaOrderPlacement(OrderPlacementMixin):

    def handle_successful_order(self, order):
        pass  # need to thing what to do here

def place_order(sender, **kwargs):
    """ collect basket, user, shipping_method and address, order_number, total
    and pass them to handle_order_placement, but first add payment events and
    sources """
    request = None  # this should save us from unneeded troubles
    session_data = None
    basket = sender
    user = basket.owner
    strategy = selector.strategy(user=user)
    basket.strategy = strategy
    amount_allocated = kwargs['OutSum']
    if 'extra' in kwargs:
        session_key  = kwargs['extra'].get('session_key', None)
        order_num =    kwargs['extra'].get('order_num', None)
        if session_key is not None:
            session = SessionStore(session_key = session_key)
            if session.session_key == session_key:
                request = HttpRequest()
                request.session = session
                request.user = user
                session_data = CheckoutSessionData(request)

    order_placement = RobokassaOrderPlacement()
    if session_data is not None:
        order_placement.checkout_session = session_data
        order_placement.request = request
        shipping_address = order_placement.get_shipping_address(basket)
        shipping_method = order_placement.get_shipping_method(
                basket, shipping_address)
        total = order_placement.get_order_totals(basket, shipping_method)

    # now create payment source and events
    source_type, is_created = SourceType.objects.get_or_create(
                name=u'Робокасса', code='robokassa')
    source = Source(source_type=source_type, 
                amount_allocated=amount_allocated)
    order_placement.add_payment_source(source)
    order_placement.add_payment_event('allocated', amount_allocated)

    # all done lets place an order
    order_placement.handle_order_placement(
                order_num, user, basket, shipping_address, shipping_method,
                total)
