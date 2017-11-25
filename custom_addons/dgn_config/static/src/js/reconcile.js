
odoo.define('dgn_config.Reconcile', function (require) {
"use strict";
var core = require('web.core');
var Reconciliation = require('account.reconciliation');
var QWeb = core.qweb;

Reconciliation.abstractReconciliation.include({

    keyboardShortcutsHandler: function(e) {
        var self = this;
        if ((e.which === 13 || e.which === 10) && (e.ctrlKey || e.metaKey)) {
            self.processReconciliations(_.filter(self.getChildren(), function(o) { return true; }));
        }
    },

});

});

