# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from dateutil.relativedelta import relativedelta
from datetime import datetime, date, timedelta
from math import floor
from odoo import http, _
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from stat_types import STAT_TYPES, FORECAST_STAT_TYPES, compute_mrr_growth_values

# We need to use the same formatting as the one in read_group (see models.py)
DISPLAY_FORMATS = {
    'day': '%d %b %Y',
    'week': 'W%W %Y',
    'week_special': '%w W%W %Y',
    'month': '%B %Y',
    'year': '%Y',
}


class RevenueKPIsDashboard(http.Controller):

    @http.route('/account_contract_dashboard/fetch_cohort_report', type='json', auth='user')
    def cohort(self, date_start, cohort_period, cohort_interest, filters):
        """
        Get a Cohort Analysis report

        :param date_start: date of the first contract to take into account
        :param cohort_period: cohort period. Between 'day','week','month', 'year'
        :param cohort_interest: cohort interest. Could be 'value' or 'number'
        :param filters: filtering on specific contract templates, tags, companies
        """

        cohort_report = []
        company_currency_id = request.env.user.company_id.currency_id

        subs_fields = ['date_start', 'recurring_total']
        subs_domain = [
            ('state', 'not in', ['draft', 'cancel']),
            ('date_start', '>=', date_start),
            ('date_start', '<=', date.today().strftime(DEFAULT_SERVER_DATE_FORMAT))]
        if filters.get('template_ids'):
            subs_domain.append(('template_id', 'in', filters.get('template_ids')))
        if filters.get('tag_ids'):
            subs_domain.append(('tag_ids', 'in', filters.get('tag_ids')))
        if filters.get('company_ids'):
            subs_domain.append(('company_id', 'in', filters.get('company_ids')))

        for cohort_group in request.env['sale.subscription']._read_group_raw(domain=subs_domain, fields=['date_start'], groupby='date_start:' + cohort_period):
            # _read_group_raw returns (range, label), with range like date1/date2
            tf = cohort_group['date_start:' + cohort_period]
            date1 = tf[0].split('/')[0]
            cohort_subs = request.env['sale.subscription'].search(cohort_group['__domain'])
            cohort_date = datetime.strptime(date1, DEFAULT_SERVER_DATE_FORMAT)

            if cohort_interest == 'value':
                starting_value = float(sum([x.currency_id.compute(x.recurring_total, company_currency_id) if x.currency_id else x.recurring_total for x in cohort_subs]))
            else:
                starting_value = float(len(cohort_subs))
            cohort_line = []

            for ij in range(0, 16):
                ij_start_date = cohort_date
                if cohort_period == 'day':
                    ij_start_date += relativedelta(days=ij)
                    ij_end_date = ij_start_date + relativedelta(days=1)
                elif cohort_period == 'week':
                    ij_start_date += relativedelta(days=7*ij)
                    ij_end_date = ij_start_date + relativedelta(days=7)
                elif cohort_period == 'month':
                    ij_start_date += relativedelta(months=ij)
                    ij_end_date = ij_start_date + relativedelta(months=1)
                else:
                    ij_start_date += relativedelta(years=ij)
                    ij_end_date = ij_start_date + relativedelta(years=1)

                if ij_start_date > datetime.today():
                    # Who can predict the future, right ?
                    cohort_line.append({
                        'value': '-',
                        'percentage': '-',
                        'domain': '',
                    })
                    continue
                significative_period = ij_start_date.strftime(DISPLAY_FORMATS[cohort_period])
                churned_subs = [x for x in cohort_subs if x.date and datetime.strptime(x.date, DEFAULT_SERVER_DATE_FORMAT).strftime(DISPLAY_FORMATS[cohort_period]) == significative_period]

                if cohort_interest == 'value':
                    churned_value = sum([x.currency_id.compute(x.recurring_total, company_currency_id) if x.currency_id else x.recurring_total for x in churned_subs])
                else:
                    churned_value = len(churned_subs)

                previous_cohort_remaining = starting_value if ij == 0 else cohort_line[-1]['value']
                cohort_remaining = previous_cohort_remaining - churned_value
                cohort_line_ij = {
                    'value': cohort_remaining,
                    'percentage': starting_value and round(100*(cohort_remaining)/starting_value, 1) or 0,
                    'domain': cohort_group['__domain'] + [
                        ("date", ">=", ij_start_date.strftime(DEFAULT_SERVER_DATE_FORMAT)),
                        ("date", "<", ij_end_date.strftime(DEFAULT_SERVER_DATE_FORMAT))]
                }
                cohort_line.append(cohort_line_ij)

            cohort_report.append({
                'period': tf[1],
                'starting_value': starting_value,
                'domain': cohort_group['__domain'],
                'values': cohort_line,
            })

        return {
            'contract_templates': request.env['sale.subscription.template'].search_read([], ['name']),
            'tags': request.env['account.analytic.tag'].search_read([], ['name']),
            'companies': request.env['res.company'].search_read([], ['name']),
            'cohort_report': cohort_report,
            'currency_id': company_currency_id.id,
        }

    @http.route('/account_contract_dashboard/fetch_data', type='json', auth='user')
    def fetch_data(self):
        # context is necessary so _(...) can translate in the appropriate language
        context = request.env.context
        return {
            'stat_types': {
                key: {
                    'name': _(stat['name']),
                    'dir': stat['dir'],
                    'code': stat['code'],
                    'prior': stat['prior'],
                    'add_symbol': stat['add_symbol'],
                }
                for key, stat in STAT_TYPES.iteritems()
            },
            'forecast_stat_types': {
                key: {
                    'name': _(stat['name']),
                    'code': stat['code'],
                    'prior': stat['prior'],
                    'add_symbol': stat['add_symbol'],
                }
                for key, stat in FORECAST_STAT_TYPES.iteritems()
            },
            'currency_id': request.env.user.company_id.currency_id.id,
            'contract_templates': request.env['sale.subscription.template'].search_read([], fields=['name']),
            'tags': request.env['account.analytic.tag'].search_read([], fields=['name']),
            'companies': request.env['res.company'].search_read([], fields=['name']),
            'has_template': bool(request.env['sale.subscription.template'].search_count([])),
            'has_def_revenues': bool(request.env['sale.subscription.template'].search([]).mapped('template_asset_category_id')),
            'has_mrr': bool(request.env['account.invoice.line'].search_count([('asset_start_date', '!=', False)])),
        }

    @http.route('/account_contract_dashboard/companies_check', type='json', auth='user')
    def companies_check(self, company_ids):
        company_ids = request.env['res.company'].browse(company_ids)
        currency_ids = company_ids.mapped('currency_id')

        if len(currency_ids) == 1:
            return {
                'result': True,
                'currency_id': currency_ids.id,
            }
        elif len(company_ids) == 0:
            message = _('No company selected.')
        elif len(currency_ids) >= 1:
            message = _('It makes no sense to sum MRR of different currencies. Please select companies with the same currency.')
        else:
            message = _('Unknown error')

        return {
            'result': False,
            'error_message': message,
        }

    @http.route('/account_contract_dashboard/get_default_values_forecast', type='json', auth='user')
    def get_default_values_forecast(self, forecast_type, end_date, filters):

        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)

        net_new_mrr = compute_mrr_growth_values(end_date, end_date, filters)['net_new_mrr']
        revenue_churn = self.compute_stat('revenue_churn', end_date, end_date, filters)

        result = {
            'expon_growth': 15,
            'churn': revenue_churn,
            'projection_time': 12,
        }

        if 'mrr' in forecast_type:
            mrr = self.compute_stat('mrr', end_date, end_date, filters)

            result['starting_value'] = mrr
            result['linear_growth'] = net_new_mrr
        else:
            arpu = self.compute_stat('arpu', end_date, end_date, filters)
            nb_contracts = self.compute_stat('nb_contracts', end_date, end_date, filters)

            result['starting_value'] = nb_contracts
            result['linear_growth'] = 0 if arpu == 0 else net_new_mrr/arpu
        return result

    @http.route('/account_contract_dashboard/get_stats_history', type='json', auth='user')
    def get_stats_history(self, stat_type, start_date, end_date, filters):

        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)

        results = {}

        for delta in [1, 3, 12]:
            results['value_' + str(delta) + '_months_ago'] = self.compute_stat(
                stat_type,
                start_date - relativedelta(months=+delta),
                end_date - relativedelta(months=+delta),
                filters)

        return results

    @http.route('/account_contract_dashboard/get_stats_by_plan', type='json', auth='user')
    def get_stats_by_plan(self, stat_type, start_date, end_date, filters):

        results = []

        domain = []
        if filters.get('template_ids'):
            domain += [('id', 'in', filters.get('template_ids'))]

        template_ids = request.env['sale.subscription.template'].search(domain)

        for template in template_ids:
            sale_subscriptions = request.env['sale.subscription'].search([('template_id', '=', template.id)])
            analytic_account_ids = [sub.analytic_account_id.id for sub in sale_subscriptions]

            lines_domain = [
                ('asset_start_date', '<=', end_date),
                ('asset_end_date', '>=', end_date),
                ('account_analytic_id', 'in', analytic_account_ids),
            ]
            if filters.get('company_ids'):
                lines_domain.append(('company_id', 'in', filters.get('company_ids')))
            recurring_invoice_line_ids = request.env['account.invoice.line'].search(lines_domain)
            specific_filters = dict(filters)  # create a copy to modify it
            specific_filters.update({'template_ids': [template.id]})
            value = self.compute_stat(stat_type, start_date, end_date, specific_filters)
            results.append({
                'name': template.name,
                'nb_customers': len(recurring_invoice_line_ids.mapped('account_analytic_id')),
                'value': value,
            })

        results = sorted((results), key=lambda k: k['value'], reverse=True)

        return results

    @http.route('/account_contract_dashboard/compute_graph_mrr_growth', type='json', auth='user')
    def compute_graph_mrr_growth(self, start_date, end_date, filters, points_limit=0):

        # By default, points_limit = 0 mean every points

        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        delta = end_date - start_date

        ticks = self._get_pruned_tick_values(range(delta.days + 1), points_limit)

        results = defaultdict(list)

        # This is rolling month calculation
        for i in ticks:
            date = start_date + timedelta(days=i)
            date_splitted = str(date).split(' ')[0]

            computed_values = compute_mrr_growth_values(date, date, filters)

            for k in ['new_mrr', 'churned_mrr', 'expansion_mrr', 'down_mrr', 'net_new_mrr']:
                results[k].append({
                    '0': date_splitted,
                    '1': computed_values[k]
                })

        return results

    @http.route('/account_contract_dashboard/compute_graph_and_stats', type='json', auth='user')
    def compute_graph_and_stats(self, stat_type, start_date, end_date, filters, points_limit=30):
        """ Returns both the graph and the stats"""

        # This avoids to make 2 RPCs instead of one
        graph = self.compute_graph(stat_type, start_date, end_date, filters, points_limit=points_limit)
        stats = self._compute_stat_trend(stat_type, start_date, end_date, filters)

        return {
            'graph': graph,
            'stats': stats,
        }

    @http.route('/account_contract_dashboard/compute_graph', type='json', auth='user')
    def compute_graph(self, stat_type, start_date, end_date, filters, points_limit=30):

        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        delta = end_date - start_date

        ticks = self._get_pruned_tick_values(range(delta.days + 1), points_limit)

        results = []
        for i in ticks:
            # METHOD NON-OPTIMIZED (could optimize it using SQL with generate_series)
            date = start_date + timedelta(days=i)
            value = self.compute_stat(stat_type, date, date, filters)

            # '0' and '1' are the keys for nvd3 to render the graph
            results.append({
                '0': str(date).split(' ')[0],
                '1': value,
            })

        return results

    def _compute_stat_trend(self, stat_type, start_date, end_date, filters):

        start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)
        start_date_delta = start_date - relativedelta(months=+1)
        end_date_delta = end_date - relativedelta(months=+1)

        value_1 = self.compute_stat(stat_type, start_date_delta, end_date_delta, filters)
        value_2 = self.compute_stat(stat_type, start_date, end_date, filters)

        perc = 0 if value_1 == 0 else round(100*(value_2 - value_1)/float(value_1), 1)

        result = {
            'value_1': str(value_1),
            'value_2': str(value_2),
            'perc': perc,
        }
        return result

    @http.route('/account_contract_dashboard/compute_stat', type='json', auth='user')
    def compute_stat(self, stat_type, start_date, end_date, filters):

        if isinstance(start_date, (str, unicode)):
            start_date = datetime.strptime(start_date, DEFAULT_SERVER_DATE_FORMAT)
        if isinstance(end_date, (str, unicode)):
            end_date = datetime.strptime(end_date, DEFAULT_SERVER_DATE_FORMAT)

        return STAT_TYPES[stat_type]['compute'](start_date, end_date, filters)

    def _get_pruned_tick_values(self, ticks, nb_desired_ticks):
        if nb_desired_ticks == 0:
            return ticks

        nb_values = len(ticks)
        keep_one_of = max(1, floor(nb_values / float(nb_desired_ticks)))

        ticks = [x for x in ticks if x % keep_one_of == 0]

        return ticks
