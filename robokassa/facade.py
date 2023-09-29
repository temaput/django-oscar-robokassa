# set encoding=utf-8
""" this is oscar frontend for using communication routines from 
django-robokassa"""

from logging import getLogger

log = getLogger('robokassa.facade')

import json
from urllib import quote
from django.core.urlresolvers import reverse
from oscar.core.loading import get_class

from robokassa.forms import RobokassaForm
from robokassa.conf import EXTRA_PARAMS, ROBOKASSA_SESSION_KEY
from robokassa.utils import DecimalMonetaryEncoder

OPTIONAL_PARAMS = ('Desc', 'IncCurrLabel', 'Email', 'Culture')
RedirectRequired = get_class('payment.exceptions', 'RedirectRequired')


def robokassa_redirect(request, basket_num, amount, receiptDTO=None, **kwargs):
    """ This will be called from PaymentDetailsView.handle_payment,
    it supposed to generate url for Robokassa, inject it into RedirectRequired
    error and raise it
    We also have to save the session and to use its number as parameter


    """

    if receiptDTO is not None:
        receiptDTO = json.dumps(receiptDTO, cls=DecimalMonetaryEncoder)
        receiptDTO = quote(receiptDTO)

        initial = {
            'OutSum': float(round(amount, 2)),
            'InvId': basket_num,
            'Receipt': receiptDTO
        }
        for key in kwargs:
            if key in EXTRA_PARAMS or key in OPTIONAL_PARAMS:
                initial[key] = kwargs[key]

        session = request.session
        session[ROBOKASSA_SESSION_KEY] = initial
        session.save()
        url = reverse('redirect')
        err = RedirectRequired(url)
        raise err
    else:
        initial = {
            'OutSum': float(round(amount, 2)),
            'InvId': basket_num,
        }
        for key in kwargs:
            if key in EXTRA_PARAMS or key in OPTIONAL_PARAMS:
                initial[key] = kwargs[key]

        session = request.session
        session.save()
        if session.session_key is not None:
            initial['session_key'] = session.session_key
        else:
            log.error('session_key is empty')

        form = RobokassaForm(initial=initial)
        err = RedirectRequired(form.get_redirect_url())
        raise err

