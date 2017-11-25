# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    helpdesk_target_closed = fields.Float(string='Target Tickets to Close')
    helpdesk_target_rating = fields.Float(string='Target Customer Rating')
    helpdesk_target_success = fields.Float(string='Target Success Rate')
