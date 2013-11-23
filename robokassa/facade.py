# set encoding=utf-8
""" this is oscar frontend for using communication routines from 
django-robokassa"""

from oscar.core.loading import get_class


from robokassa.forms import RobokassaForm
from robokassa.conf import EXTRA_PARAMS
RedirectRequired = get_class('oscar.apps.payment.exceptions','RedirectRequired')

def pre_auth(basket_num, amount, **kwargs):
    """ This will be called from PaymentDetailsView.handle_payment,
    it supposed to generate url for Robokassa, inject it into RedirectRequired
    error and raise it
    """
    initial={'OutSum': amount, 'InvId': basket_num}
    for key in kwargs:
        if key in EXTRA_PARAMS:
            initial[key] = kwargs[key]

    form = RobokassaForm(initial=initial)
    err = RedirectRequired(form.get_redirect_url())
    raise err




