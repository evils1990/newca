
odoo.define('dgn_config.ChangeKanbanColor', function (require) {
"use strict";

var core = require('web.core');
var data = require('web.data');
var formats = require('web.formats');
var framework = require('web.framework');
var session = require('web.session');
var time = require('web.time');
var utils = require('web.utils');
var Widget = require('web.Widget');
var kanban_widgets = require('web_kanban.widgets');
var QWeb = core.qweb;
var fields_registry = kanban_widgets.registry;

var KanbanRecord = require('web_kanban.Record');

var KanbanRecord_child = KanbanRecord.include({

    kanban_getcolor: function(variable) {
        if (typeof(variable) === 'number') {
            return variable;
        }
        if (typeof(variable) === 'string') {
            var index = 0;
            for (var i=0; i<variable.length; i++) {
                index += variable.charCodeAt(i);
            }
            return index;
        }
        return 0;
    },

});

});

