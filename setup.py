#!/usr/bin/env python
#coding: utf-8
from distutils.core import setup

import sys
reload(sys).setdefaultencoding("UTF-8")

setup(
    name='django-oscar-robokassa',
    version='0.1.7',
    author='Mikhail Korobov',
    author_email='kmike84@gmail.com',

    packages=['robokassa', 'robokassa.migrations'],
    package_data = {'robokassa.migrations': ['*.json']},

    url='http://github.com/temaput/django-oscar-robokassa',
    license = 'MIT license',
    description = u'Приложение для интеграции платежной системы ROBOKASSA в проекты на основе django-oscar'.encode('utf8'),
    long_description = open('README.rst').read().decode('utf8') + open('CHANGES.rst').read().decode('utf8'),

    requires=['django (>= 1.5)', 'oscar (>=0.6)'],
    obsoletes=['robokassa (<=1.1)'],

    classifiers=(
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Natural Language :: Russian',
    ),
)
