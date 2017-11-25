# -*- coding: utf-8 -*-
from odoo.release import version_info
try:
    import models       # noqa
    import controllers  # noqa
except ImportError:
    if version_info >= (8, 'saas~6'):
        raise
