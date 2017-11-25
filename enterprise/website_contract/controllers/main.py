# -*- coding: utf-8 -*-
import datetime
from collections import OrderedDict
from dateutil.relativedelta import relativedelta
from werkzeug.exceptions import NotFound
from odoo import http
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.website_portal.controllers.main import website_account
from odoo.addons.website_quote.controllers.main import sale_quote


class website_account(website_account):

    def _get_contract_domain(self, partner):
        return [
            ('partner_id.id', 'in', [partner.id, partner.commercial_partner_id.id]),
            ('state', '!=', 'cancel'),
        ]

    @http.route()
    def account(self, **kw):
        """ Add contract details to main account page """
        response = super(website_account, self).account()
        partner = request.env.user.partner_id
        account_res = request.env['sale.subscription']
        contract_count = account_res.search_count(self._get_contract_domain(partner))
        response.qcontext.update({'contract_count': contract_count})

        return response

    @http.route(['/my/contract', '/my/contract/page/<int:page>'], type='http', auth="user", website=True)
    def my_contract(self, page=1, date_begin=None, date_end=None, select=None, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        SaleSubscription = request.env['sale.subscription']

        domain = self._get_contract_domain(partner)

        archive_groups = self._get_archive_groups('sale.subscription', domain)
        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        filters = {
            'all': {'label': _('All'), 'domain': []},
            'open': {'label': _('In Progress'), 'domain': [('state', '=', 'open')]},
            'pending': {'label': _('To Renew'), 'domain': [('state', '=', 'pending')]},
            'close': {'label': _('Closed'), 'domain': [('state', '=', 'close')]},
        }

        sortings = {
            'date': {'label': _('Newest'), 'order': 'create_date desc, id desc'},
            'name': {'label': _('Name'), 'order': 'name asc, id asc'}
        }

        domain += filters.get(select, filters['all'])['domain']
        order = sortings.get(sortby, sortings['date'])['order']

        # pager
        account_count = SaleSubscription.search_count(domain)
        pager = request.website.pager(
            url="/my/contract",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'select': select},
            total=account_count,
            page=page,
            step=self._items_per_page
        )

        accounts = SaleSubscription.search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        values.update({
            'accounts': accounts,
            'page_name': 'contract',
            'pager': pager,
            'archive_groups': archive_groups,
            'sortings': sortings,
            'sortby': sortby,
            'filters': OrderedDict(sorted(filters.items())),
            'select': select,
            'default_url': '/my/contract',
        })
        return request.render("website_contract.portal_my_contracts", values)


class website_contract(http.Controller):

    @http.route(['/my/contract/<int:account_id>/',
                 '/my/contract/<int:account_id>/<string:uuid>'], type='http', auth="public", website=True)
    def contract(self, account_id, uuid='', message='', message_class='', **kw):
        request.env['res.users'].browse(request.uid).has_group('sales_team.group_sale_salesman')
        account_res = request.env['sale.subscription']
        template_res = request.env['sale.subscription.template']
        if uuid:
            account = account_res.sudo().browse(account_id)
            if uuid != account.uuid or account.state == 'cancelled':
                raise NotFound()
            if request.uid == account.partner_id.user_id.id:
                account = account_res.browse(account_id)
        else:
            account = account_res.browse(account_id)

        acquirers = list(request.env['payment.acquirer'].search([('website_published', '=', True), ('registration_view_template_id', '!=', False)]))
        acc_pm = account.payment_token_id
        part_pms = account.partner_id.payment_token_ids
        inactive_options = account.sudo().recurring_inactive_lines
        display_close = account.template_id.sudo().user_closable and account.state != 'close'
        active_plan = account.template_id.sudo()
        periods = {'daily': 'days', 'weekly': 'weeks', 'monthly': 'months', 'yearly': 'years'}
        if account.recurring_rule_type != 'weekly':
            rel_period = relativedelta(datetime.datetime.today(), datetime.datetime.strptime(account.recurring_next_date, '%Y-%m-%d'))
            missing_periods = getattr(rel_period, periods[account.recurring_rule_type]) + 1
        else:
            delta = datetime.datetime.today() - datetime.datetime.strptime(account.recurring_next_date, '%Y-%m-%d')
            missing_periods = delta.days / 7
        dummy, action = request.env['ir.model.data'].get_object_reference('sale_contract', 'sale_subscription_action')
        account_templates = template_res.sudo().search([
            ('user_selectable', '=', True),
            ('id', '!=', active_plan.id),
            ('tag_ids', 'in', account.sudo().template_id.tag_ids.ids)
        ])
        values = {
            'account': account,
            'template': account.template_id.sudo(),
            'display_close': display_close,
            'close_reasons': request.env['sale.subscription.close.reason'].search([]),
            'missing_periods': missing_periods,
            'inactive_options': inactive_options,
            'payment_mandatory': active_plan.payment_mandatory,
            'user': request.env.user,
            'acquirers': acquirers,
            'acc_pm': acc_pm,
            'part_pms': part_pms,
            'is_salesman': request.env['res.users'].sudo(request.uid).has_group('sales_team.group_sale_salesman'),
            'action': action,
            'message': message,
            'message_class': message_class,
            'display_change_plan': len(account_templates) > 0,
            'pricelist': account.pricelist_id.sudo(),
        }
        render_context = {
            'json': True,
            'submit_class': 'btn btn-primary btn-sm mb8 mt8 pull-right',
            'submit_txt': 'Pay Subscription',
            'bootstrap_formatting': True
        }
        render_context = dict(values.items() + render_context.items())
        for acquirer in acquirers:
            acquirer.form = acquirer.sudo()._registration_render(account.partner_id.id, render_context)
        return request.render("website_contract.contract", values)

    payment_succes_msg = 'message=Thank you, your payment has been validated.&message_class=alert-success'
    payment_fail_msg = 'message=There was an error with your payment, please try with another payment method or contact us.&message_class=alert-danger'

    @http.route(['/my/contract/payment/<int:account_id>/',
                 '/my/contract/payment/<int:account_id>/<string:uuid>'], type='http', auth="public", methods=['POST'], website=True)
    def payment(self, account_id, uuid=None, **kw):
        account_res = request.env['sale.subscription']
        invoice_res = request.env['account.invoice']
        get_param = ''
        if uuid:
            account = account_res.sudo().browse(account_id)
            if uuid != account.uuid:
                raise NotFound()
        else:
            account = account_res.browse(account_id)

        # no change
        if int(kw.get('pay_meth', 0)) > 0:
            account.payment_token_id = int(kw['pay_meth'])

        # we can't call _recurring_invoice because we'd miss 3DS, redoing the whole payment here
        payment_token = account.payment_token_id
        if payment_token:
            invoice_values = account.sudo()._prepare_invoice()
            new_invoice = invoice_res.sudo().create(invoice_values)
            new_invoice.compute_taxes()
            tx = account.sudo()._do_payment(payment_token, new_invoice)[0]
            if tx.html_3ds:
                return tx.html_3ds
            get_param = self.payment_succes_msg if tx.state in ['done', 'authorized'] else self.payment_fail_msg
            if tx.state in ['done', 'authorized']:
                account.send_success_mail(tx, new_invoice)
                msg_body = 'Manual payment succeeded. Payment reference: <a href=# data-oe-model=payment.transaction data-oe-id=%d>%s</a>; Amount: %s. Invoice <a href=# data-oe-model=account.invoice data-oe-id=%d>View Invoice</a>.' % (tx.id, tx.reference, tx.amount, new_invoice.id)
                account.message_post(body=msg_body)
            else:
                new_invoice.unlink()

        return request.redirect('/my/contract/%s/%s?%s' % (account.id, account.uuid, get_param))

    # 3DS controllers
    # transaction began as s2s but we receive a form reply
    # TODO: in master, only support uuid submission (not id)
    # DO NOT FORWARD-PORT TO MASTER (stop at version 10.0)
    @http.route(['/my/contract/<account_id>/payment/<int:tx_id>/accept/',
                 '/my/contract/<account_id>/payment/<int:tx_id>/decline/',
                 '/my/contract/<account_id>/payment/<int:tx_id>/exception/'], type='http', auth="public", website=True)
    def payment_accept(self, account_id, tx_id, **kw):
        Subscription = request.env['sale.subscription']
        tx_res = request.env['payment.transaction']
        try:
            account = Subscription.sudo().browse(int(account_id))
        except ValueError:
            account = Subscription.sudo().search([('uuid', '=', account_id)])

        tx = tx_res.sudo().browse(tx_id)

        get_param = self.payment_succes_msg if tx.state in ['done', 'authorized'] else self.payment_fail_msg

        if isinstance(account_id, int):  # called by id: no-sudo redirect
            redirect_url = '/my/contract/%s?%s' % (account.id, get_param)
        else:
            redirect_url = '/my/contract/%s/%s?%s' % (account.id, account.uuid, get_param)
        return request.redirect(redirect_url)

    @http.route(['/my/contract/<int:account_id>/change'], type='http', auth="public", website=True)
    def change_contract(self, account_id, uuid=None, **kw):
        account_res = request.env['sale.subscription']
        template_res = request.env['sale.subscription.template']
        account = account_res.sudo().browse(account_id)
        if uuid != account.uuid:
            raise NotFound()
        if account.state == 'close':
            return request.redirect('/my/contract/%s' % account_id)
        if kw.get('new_template_id'):
            new_template_id = int(kw.get('new_template_id'))
            periods = {'daily': 'Day(s)', 'weekly': 'Week(s)', 'monthly': 'Month(s)', 'yearly': 'Year(s)'}
            msg_before = [account.sudo().template_id.name,
                          str(account.recurring_total),
                          str(account.recurring_interval) + ' ' + str(periods[account.recurring_rule_type])]
            account.sudo().change_subscription(new_template_id)
            msg_after = [account.sudo().template_id.name,
                         str(account.recurring_total),
                         str(account.recurring_interval) + ' ' + str(periods[account.recurring_rule_type])]
            msg_body = request.env['ir.ui.view'].render_template('website_contract.chatter_change_contract',
                                                                 values={'msg_before': msg_before, 'msg_after': msg_after})
            # price options are about to change and are not propagated to existing sale order: reset the SO
            order = request.website.sudo().sale_get_order()
            if order:
                order.reset_project_id()
            account.message_post(body=msg_body)
            return request.redirect('/my/contract/%s/%s' % (account.id, account.uuid))
        account_templates = template_res.sudo().search([
            ('user_selectable', '=', True),
            ('tag_ids', 'in', account.template_id.tag_ids.ids)
        ])
        values = {
            'account': account,
            'pricelist': account.pricelist_id,
            'active_template': account.template_id,
            'inactive_templates': account_templates,
            'user': request.env.user,
        }
        return request.render("website_contract.change_template", values)

    @http.route(['/my/contract/<int:account_id>/close'], type='http', methods=["POST"], auth="public", website=True)
    def close_account(self, account_id, uuid=None, **kw):
        account_res = request.env['sale.subscription']

        if uuid:
            account = account_res.sudo().browse(account_id)
            if uuid != account.uuid:
                raise NotFound()
        else:
            account = account_res.browse(account_id)

        if account.sudo().template_id.user_closable:
            close_reason = request.env['sale.subscription.close.reason'].browse(int(kw.get('close_reason_id')))
            account.close_reason_id = close_reason
            if kw.get('closing_text'):
                account.message_post(_('Closing text : ') + kw.get('closing_text'))
            account.set_close()
            account.date = datetime.date.today().strftime('%Y-%m-%d')
        return request.redirect('/my/home')

    @http.route(['/my/contract/<int:account_id>/add_option'], type='http', methods=["POST"], auth="public", website=True)
    def add_option(self, account_id, uuid=None, **kw):
        option_res = request.env['sale.subscription.template.option']
        account_res = request.env['sale.subscription']
        if uuid:
            account = account_res.sudo().browse(account_id)
            if uuid != account.uuid:
                raise NotFound()
        else:
            account = account_res.browse(account_id)
        new_option_id = int(kw.get('new_option_id'))
        new_option = option_res.sudo().browse(new_option_id)
        pricelist = request.website.get_current_pricelist()
        price = new_option.with_context(pricelist_id=pricelist.id).price
        if not price or not price * account.partial_recurring_invoice_ratio() or not account.template_id.partial_invoice:
            account.sudo().add_option(new_option_id)
            msg_body = request.env['ir.ui.view'].render_template('website_contract.chatter_add_option',
                                                                 values={'new_option': new_option, 'price': price})
            account.message_post(body=msg_body)
        return request.redirect('/my/contract/%s/%s' % (account.id, account.uuid))

    @http.route(['/my/contract/<int:account_id>/remove_option'], type='http', methods=["POST"], auth="public", website=True)
    def remove_option(self, account_id, uuid=None, **kw):
        remove_option_id = int(kw.get('remove_option_id'))
        option_res = request.env['sale.subscription.template.option']
        account_res = request.env['sale.subscription']
        if uuid:
            remove_option = option_res.sudo().browse(remove_option_id)
            account = account_res.sudo().browse(account_id)
            if uuid != account.uuid:
                raise NotFound()
        else:
            remove_option = option_res.browse(remove_option_id)
            account = account_res.browse(account_id)
        if remove_option.portal_access != "both" and not request.env.user.has_group('sales_team.group_sale_salesman'):
            return request.render("website.403")
        account.sudo().remove_option(remove_option_id)
        msg_body = request.env['ir.ui.view'].render_template('website_contract.chatter_remove_option',
                                                             values={'remove_option': remove_option})
        account.message_post(body=msg_body)
        return request.redirect('/my/contract/%s/%s' % (account.id, account.uuid))

    @http.route(['/my/contract/<int:account_id>/pay_option'], type='http', methods=["POST"], auth="public", website=True)
    def pay_option(self, account_id, **kw):
        order = request.website.sale_get_order(force_create=True)
        order.set_project_id(account_id)
        new_option_id = int(kw.get('new_option_id'))
        new_option = request.env['sale.subscription.template.option'].sudo().browse(new_option_id)
        account = request.env['sale.subscription'].browse(account_id)
        account.sudo().partial_invoice_line(order, new_option)

        return request.redirect("/shop/cart")

    @http.route(['/my/template/<int:template_id>'], type='http', auth="user", website=True)
    def view_template(self, template_id, **kw):
        template_res = request.env['sale.subscription.template']
        dummy, action = request.env['ir.model.data'].get_object_reference('sale_contract', 'sale_subscription_template_action')
        template = template_res.browse(template_id)
        values = {
            'template': template,
            'action': action
        }
        return request.render('website_contract.preview_template', values)


class sale_quote_contract(sale_quote):
    @http.route([
        "/quote/<int:order_id>",
        "/quote/<int:order_id>/<token>"
    ], type='http', auth="public", website=True)
    def view(self, order_id, pdf=None, token=None, message=False, **kw):
        response = super(sale_quote_contract, self).view(order_id, pdf, token, message, **kw)
        if 'quotation' in response.qcontext:  # check if token identification was ok in super
            order = response.qcontext['quotation']
            recurring_products = True in [line.product_id.recurring_invoice for line in order.sudo().order_line]
            tx_type = order._get_payment_type()
            # re-render the payment buttons with the proper tx_type if recurring products
            if 'acquirers' in response.qcontext and tx_type != 'form':
                response.qcontext['recurring_products'] = recurring_products
        return response
