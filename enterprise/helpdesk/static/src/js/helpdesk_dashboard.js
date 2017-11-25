odoo.define('helpdesk.dashboard', function (require) {
"use strict";

var core = require('web.core');
var formats = require('web.formats');
var Model = require('web.Model');
var session = require('web.session');
var KanbanView = require('web_kanban.KanbanView');

var QWeb = core.qweb;

var _t = core._t;
var _lt = core._lt;

var HelpdeskTeamDashboardView = KanbanView.extend({
    display_name: _lt('Dashboard'),
    icon: 'fa-dashboard',
    view_type: "helpdesk_dashboard",
    searchview_hidden: true,
    events: {
        'click .o_dashboard_action': 'on_dashboard_action_clicked',
        'click .o_target_to_set': 'on_dashboard_helpdesk_target_clicked',
    },

    fetch_data: function() {
        return new Model('helpdesk.team')
            .call('retrieve_dashboard', []);
    },

    render: function() {
        var super_render = this._super;
        var self = this;

        return this.fetch_data().then(function(result){
            self.show_demo = result && result['show_demo'];
            self.rating_enable = result && result['rating_enable'];
            self.success_rate_enable = result && result['success_rate_enable'];

            var helpdesk_dashboard = QWeb.render('helpdesk.HelpdeskDashboard', {
                widget: self,
                show_demo: self.show_demo,
                rating_enable: self.rating_enable,
                success_rate_enable: self.success_rate_enable,
                values: result,
            });
            super_render.call(self);
            $(helpdesk_dashboard).prependTo(self.$el);
        });
    },

    on_dashboard_action_clicked: function(ev){
        ev.preventDefault();
        var self = this;
        var $action = $(ev.currentTarget);
        var action_name = $action.attr('name');
        var action_extra = $action.data('extra');
        var additional_context = {}

        if ('helpdesk_rating_today' == action_name || 'helpdesk_rating_7days' == action_name){
            new Model(self.model)
                .call(action_name)
                .then(function(data) {
                    if (data){
                       self.do_action(data, {additional_context: additional_context});
                    }
                });
        }

        new Model("ir.model.data")
            .call("xmlid_to_res_id", [action_name])
            .then(function(data) {
                if (data){
                   self.do_action(data, {additional_context: additional_context});
                }
            });
    },

    on_change_helpdesk_input_target: function(e) {
        var self = this;
        var $input = $(e.target);
        var target_name = $input.attr('name');
        var target_value = $input.val();

        if(isNaN(target_value)) {
            this.do_warn(_t("Wrong value entered!"), _t("Only Integer Value should be valid."));
        } else {
            this._updated = new Model('helpdesk.team')
                            .call('modify_target_helpdesk_team_dashboard', [target_name, parseInt(target_value)])
                            .then(function() {
                                return self.render();
                            });
        }
    },

    on_dashboard_helpdesk_target_clicked: function(ev){
        if (this.show_demo) {
            // The user is not allowed to modify the targets in demo mode
            return;
        }

        var self = this;
        var $target = $(ev.currentTarget);
        var target_name = $target.attr('name');
        var target_value = $target.attr('value');

        var $input = $('<input/>', {type: "text"});
        $input.attr('name', target_name);
        if (target_value) {
            $input.attr('value', target_value);
        }
        $input.on('keyup input', function(e) {
            if(e.which === $.ui.keyCode.ENTER) {
                self.on_change_helpdesk_input_target(e);
            }
        });
        $input.on('blur', function(e) {
            self.on_change_helpdesk_input_target(e);
        });

        $.when(this._updated).then(function() {
            $input.replaceAll(self.$('.o_target_to_set[name=' + target_name + ']')) // the target may have changed (re-rendering)
                  .focus()
                  .select();
        });
    },

});

core.view_registry.add('helpdesk_dashboard', HelpdeskTeamDashboardView);

return HelpdeskTeamDashboardView

});
