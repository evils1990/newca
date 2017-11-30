#-*- coding: utf-8 -*-

from odoo import fields,models


class CrmTeam(models.Model):
    _inherit = 'crm.team'
    crm_type=fields.Selection([('internal','Internal'),('agency','Agency'),('collab','Collaborator')],'Type')
    parent_id=fields.Many2one('crm.team','Parent Team')
	pricelist_id=fields.Many2one('product.pricelist','Price list')

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'
    team_id=fields.One2many('crm.team','pricelist_id','Sale Team')