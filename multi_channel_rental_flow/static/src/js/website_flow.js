/**
 * Website Rental Flow — product detail page logic.
 *
 * Handles duration selection, datepicker, slot selection and
 * add-to-basket. All pricing is computed server-side.
 *
 * Reads config from #rf-interactive data attributes.
 */

var T = (typeof TRANSLATIONS !== 'undefined') ? TRANSLATIONS : {};
var LANG = (typeof CURRENT_LANG !== 'undefined' && CURRENT_LANG) ? CURRENT_LANG.replace('_', '-') : 'en';

var rf = {
    productId: 0, profileId: 0, itemRole: '', currency: '',
    requiresTimeslot: false, requiresDuration: false, allowQty: true,
    listPrice: 0,
    quantity: 1,
    durations: [], selectedDuration: null,
    calendarMonth: new Date(),
    dayStates: {}, selectedDate: null,
    slots: [], selectedSlot: null,
    selectedEvent: null,
};

document.addEventListener('DOMContentLoaded', function() {
    var el = document.getElementById('rf-interactive');
    if (!el) return;

    rf.productId = parseInt(el.dataset.productId);
    rf.profileId = parseInt(el.dataset.profileId);
    rf.itemRole = el.dataset.itemRole;
    rf.currency = el.dataset.currency || '';
    rf.requiresTimeslot = el.dataset.requiresTimeslot === '1';
    rf.requiresDuration = el.dataset.requiresDuration === '1';
    rf.allowQty = el.dataset.allowQty === '1';
    rf.listPrice = parseFloat(el.dataset.listPrice) || 0;

    if (!rf.allowQty) document.getElementById('rf-qty-section').classList.add('d-none');

    if (rf.itemRole === 'event_ticket') {
        // Event flow: show event list first, calendar appears after selection
        document.getElementById('rf-event-section').classList.remove('d-none');
        rfLoadEvents();
    } else if (rf.itemRole === 'addon' || rf.itemRole === 'service') {
        document.getElementById('rf-add-section').classList.remove('d-none');
        rfUpdateAddPrice(rf.listPrice * rf.quantity);
    } else {
        // Rental flow: show duration + calendar
        if (rf.requiresDuration) {
            document.getElementById('rf-dur-section').classList.remove('d-none');
            rfLoadDurations();
        }
        if (rf.requiresTimeslot) {
            document.getElementById('rf-cal-section').classList.remove('d-none');
            rfRenderCalendar();
        }
    }
});

// RPC helper
async function rfRpc(url, params) {
    var resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({jsonrpc:'2.0', method:'call', id:1, params:params}),
    });
    var data = await resp.json();
    if (data.error) throw new Error(data.error.data?.message || data.error.message);
    return data.result;
}

// Quantity
function rfChangeQty(delta) {
    rf.quantity = Math.max(1, rf.quantity + delta);
    document.getElementById('rf-qty-val').textContent = rf.quantity;
    if (rf.itemRole === 'event_ticket' && rf.selectedEvent) {
        // Refresh event calendar with new quantity — rfSelectEventDate
        // will show/hide add button based on slot availability
        rfRenderEventCalendar(rf.selectedEvent.eventId);
        if (rf.selectedDate) {
            rfSelectEventDate(rf.selectedDate);
        } else {
            document.getElementById('rf-add-section').classList.add('d-none');
        }
    } else if (rf.selectedDate && rf.requiresTimeslot) {
        rfLoadSlots();
        rfRenderCalendar();
    }
    if (rf.selectedSlot !== null && rf.itemRole !== 'event_ticket') rfUpdateSlotSelection();
    if (rf.itemRole === 'addon' || rf.itemRole === 'service') {
        rfUpdateAddPrice(rf.listPrice * rf.quantity);
    }
}

// Durations
async function rfLoadDurations() {
    var res = await rfRpc('/rental-flow/api/durations', {product_id: rf.productId});
    rf.durations = res.durations;
    var el = document.getElementById('rf-dur-list');
    el.innerHTML = '';
    rf.durations.forEach(function(d, i) {
        el.innerHTML += '<button class="btn btn-sm ' + (i===0?'btn-primary':'btn-outline-secondary') +
            '" onclick="rfSelectDuration(' + i + ')">' + escH(d.label) + '</button>';
    });
    if (rf.durations.length > 0) rfSelectDuration(0);
}

function rfSelectDuration(index) {
    rf.selectedDuration = rf.durations[index];
    var btns = document.querySelectorAll('#rf-dur-list .btn');
    btns.forEach(function(b,i) {
        b.className = 'btn btn-sm ' + (i===index?'btn-primary':'btn-outline-secondary');
    });
    rfRenderCalendar();
    if (rf.selectedDate) rfLoadSlots();
}

// Calendar
async function rfRenderCalendar() {
    var month = rf.calendarMonth;
    document.getElementById('rf-cal-month').textContent =
        month.toLocaleString(LANG || 'en', {month:'long', year:'numeric'});

    var centerStr = month.getFullYear() + '-' +
        String(month.getMonth()+1).padStart(2,'0') + '-15';
    var res = await rfRpc('/rental-flow/api/day-states', {
        product_id: rf.productId,
        center_date_str: centerStr,
        duration_value: rf.selectedDuration ? rf.selectedDuration.value : null,
        duration_unit: rf.selectedDuration ? rf.selectedDuration.unit : null,
        quantity: rf.quantity,
        item_role: rf.itemRole,
    });
    rf.dayStates = {};
    res.days.forEach(function(d) { rf.dayStates[d.date] = d; });

    var grid = document.getElementById('rf-cal-grid');
    grid.innerHTML = '';
    [T.mon||'Mon', T.tue||'Tue', T.wed||'Wed', T.thu||'Thu', T.fri||'Fri', T.sat||'Sat', T.sun||'Sun'].forEach(function(d) {
        grid.innerHTML += '<div class="rf-cal-day-hdr">' + d + '</div>';
    });
    var first = new Date(month.getFullYear(), month.getMonth(), 1);
    var dow = (first.getDay()+6)%7;
    for (var i=0;i<dow;i++) grid.innerHTML += '<div></div>';
    var days = new Date(month.getFullYear(), month.getMonth()+1, 0).getDate();
    for (var d=1;d<=days;d++) {
        var ds = month.getFullYear()+'-'+String(month.getMonth()+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
        var info = rf.dayStates[ds];
        var cls = 'rf-cal-day ';
        var clickable = false;
        var style = '';
        if (!info || info.day_state==='closed') {
            style = 'background:#e9ecef;color:#adb5bd;cursor:not-allowed;';
        } else if (info.day_state==='unavailable') {
            style = 'background:#dc3545;color:#fff;cursor:not-allowed;';
        } else {
            style = 'background:' + (info.color_code||'#28a745') + ';color:#fff;';
            clickable = true;
        }
        if (rf.selectedDate===ds) cls += 'selected';
        grid.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (clickable?' onclick="rfSelectDate(\''+ds+'\')"':'') +
            '><strong>'+d+'</strong></div>';
    }
}

function rfCalNav(delta) {
    rf.calendarMonth = new Date(rf.calendarMonth.getFullYear(), rf.calendarMonth.getMonth()+delta, 1);
    rfRenderCalendar();
}

async function rfSelectDate(ds) {
    rf.selectedDate = ds;
    var d = new Date(ds+'T00:00:00');
    var display = d.toLocaleDateString(LANG || 'en', {weekday:'long',day:'numeric',month:'long',year:'numeric'});
    document.getElementById('rf-selected-date').textContent = (T.selected || 'Selected: ') + display;
    document.getElementById('rf-slot-date').textContent = display;
    rfRenderCalendar();
    await rfLoadSlots();
}

// Slots
async function rfLoadSlots() {
    if (!rf.selectedDate) return;
    document.getElementById('rf-slot-section').classList.remove('d-none');
    document.getElementById('rf-slot-grid').innerHTML = '<div class="text-center text-muted py-3">' + (T.loading || 'Loading...') + '</div>';
    var res = await rfRpc('/rental-flow/api/slots', {
        product_id: rf.productId,
        date_str: rf.selectedDate,
        duration_value: rf.selectedDuration ? rf.selectedDuration.value : null,
        duration_unit: rf.selectedDuration ? rf.selectedDuration.unit : null,
        quantity: rf.quantity,
        item_role: rf.itemRole,
    });
    rf.slots = res.slots;
    rf.selectedSlot = null;
    rfRenderSlots();
}

function rfRenderSlots() {
    var el = document.getElementById('rf-slot-grid');
    el.innerHTML = '';
    if (!rf.slots.length) { el.innerHTML = '<p class="text-muted">' + (T.no_slots || 'No slots available.') + '</p>'; return; }
    rf.slots.forEach(function(s, i) {
        var sel = s.selectable !== false;
        var cls = 'rf-slot ' + (sel?'':'unavailable') + (rf.selectedSlot===i?' selected':'');
        var style = 'background:'+(s.color_code||'#6c757d')+';';
        if (!sel) style += 'opacity:0.4;';
        el.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (sel?' onclick="rfSelectSlot('+i+')"':'') + '>' +
            '<strong>'+(s.start_display||'')+'</strong><br/>' +
            '<small>'+(s.price_unit||0).toFixed(2)+' '+escH(rf.currency)+'</small><br/>' +
            (s.available_qty!==undefined?'<small>'+s.available_qty+' '+(T.available||'available')+'</small>':'') +
            '</div>';
    });
}

function rfSelectSlot(i) {
    rf.selectedSlot = i;
    rfRenderSlots();
    rfUpdateSlotSelection();
}

function rfUpdateSlotSelection() {
    var s = rf.slots[rf.selectedSlot];
    if (!s || s.selectable === false) {
        document.getElementById('rf-add-section').classList.add('d-none');
        var avail = s ? (s.available_qty || s.seats_available || 0) : 0;
        rfShowAvailWarning(avail);
        rf.selectedSlot = null;
        return;
    }
    rfHideAvailWarning();
    document.getElementById('rf-add-section').classList.remove('d-none');
    rfUpdateAddPrice(s.price_unit * rf.quantity);
}

function rfShowAvailWarning(available) {
    var el = document.getElementById('rf-avail-warning');
    var txt = document.getElementById('rf-avail-warning-text');
    if (el) {
        txt.textContent = ' ' + (T.avail_only||'Only') + ' ' + available + ' ' + (T.avail_available_for||'available for the selected timeslot, but') + ' ' + rf.quantity + ' ' + (T.avail_requested||'requested.');
        el.classList.remove('d-none');
    }
}
function rfHideAvailWarning() {
    var el = document.getElementById('rf-avail-warning');
    if (el) el.classList.add('d-none');
}

function rfUpdateAddPrice(total) {
    document.getElementById('rf-add-price').textContent = total.toFixed(2) + ' ' + rf.currency;
}

// Events
async function rfLoadEvents() {
    var res = await rfRpc('/rental-flow/api/events', {product_id: rf.productId});
    rf.events = res.events || [];
    var el = document.getElementById('rf-event-list');
    el.innerHTML = '';
    if (!rf.events.length) {
        el.innerHTML = '<p class="text-muted">' + (T.no_events || 'No events available.') + '</p>';
        return;
    }
    rf.events.forEach(function(ev) {
        el.innerHTML += '<div class="card mb-2" style="cursor:pointer;" ' +
            'onclick="rfSelectEvent('+ev.event_id+','+ev.ticket_id+','+ev.price+','+(ev.price_excl||ev.price)+')">' +
            '<div class="card-body py-2">' +
            '<strong>'+escH(ev.event_name)+'</strong>' +
            '<span class="badge bg-secondary ms-2">'+escH(ev.ticket_name)+'</span>' +
            '<span class="float-end text-success fw-bold">'+ev.price.toFixed(2)+' '+escH(rf.currency)+'</span>' +
            '</div></div>';
    });

    // Auto-select the event with the lowest price
    if (rf.events.length > 0) {
        var cheapest = rf.events.reduce(function(a, b) {
            return (a.price_excl || a.price) < (b.price_excl || b.price) ? a : b;
        });
        rfSelectEvent(cheapest.event_id, cheapest.ticket_id, cheapest.price, cheapest.price_excl || cheapest.price);
    }
}

async function rfSelectEvent(eventId, ticketId, priceIncl, priceExcl) {
    rf.selectedEvent = {eventId: eventId, ticketId: ticketId, price: priceIncl, priceExcl: priceExcl};

    // Show calendar for this event
    document.getElementById('rf-cal-section').classList.remove('d-none');

    // Set calendar month to event start date
    var ev = rf.events.find(function(e) { return e.event_id === eventId; });
    if (ev && ev.date_begin) {
        var evDate = new Date(ev.date_begin);
        rf.calendarMonth = new Date(evDate.getFullYear(), evDate.getMonth(), 1);
    }

    await rfRenderEventCalendar(eventId);
}

async function rfRenderEventCalendar(eventId) {
    var month = rf.calendarMonth;
    document.getElementById('rf-cal-month').textContent =
        month.toLocaleString(LANG || 'en', {month:'long', year:'numeric'});

    var centerStr = month.getFullYear() + '-' +
        String(month.getMonth()+1).padStart(2,'0') + '-15';

    var res = await rfRpc('/rental-flow/api/day-states', {
        product_id: rf.productId,
        center_date_str: centerStr,
        quantity: rf.quantity,
        item_role: 'event_ticket',
        event_id: eventId,
    });
    rf.dayStates = {};
    res.days.forEach(function(d) { rf.dayStates[d.date] = d; });

    var grid = document.getElementById('rf-cal-grid');
    grid.innerHTML = '';
    [T.mon||'Mon', T.tue||'Tue', T.wed||'Wed', T.thu||'Thu', T.fri||'Fri', T.sat||'Sat', T.sun||'Sun'].forEach(function(d) {
        grid.innerHTML += '<div class="rf-cal-day-hdr">' + d + '</div>';
    });
    var first = new Date(month.getFullYear(), month.getMonth(), 1);
    var dow = (first.getDay()+6)%7;
    for (var i=0;i<dow;i++) grid.innerHTML += '<div></div>';
    var days = new Date(month.getFullYear(), month.getMonth()+1, 0).getDate();
    var firstAvailable = null;
    for (var d=1;d<=days;d++) {
        var ds = month.getFullYear()+'-'+String(month.getMonth()+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
        var info = rf.dayStates[ds];
        var cls = 'rf-cal-day ';
        var clickable = false;
        var style = '';
        if (!info || info.day_state==='closed') {
            style = 'background:#e9ecef;color:#adb5bd;cursor:not-allowed;';
        } else if (info.day_state==='unavailable' || info.available_slot_count===0) {
            style = 'background:#dc3545;color:#fff;cursor:not-allowed;';
        } else {
            style = 'background:' + (info.color_code||'#28a745') + ';color:#fff;';
            clickable = true;
            if (!firstAvailable) firstAvailable = ds;
        }
        if (rf.selectedDate===ds) cls += 'selected';
        grid.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (clickable?' onclick="rfSelectEventDate(\''+ds+'\')"':'') +
            '><strong>'+d+'</strong></div>';
    }

    // Auto-select first available date
    if (firstAvailable && !rf.selectedDate) {
        rfSelectEventDate(firstAvailable);
    }
}

async function rfSelectEventDate(ds) {
    rf.selectedDate = ds;
    var d = new Date(ds+'T00:00:00');
    var display = d.toLocaleDateString(LANG || 'en', {weekday:'long',day:'numeric',month:'long',year:'numeric'});
    document.getElementById('rf-selected-date').textContent = (T.selected || 'Selected: ') + display;
    document.getElementById('rf-slot-date').textContent = display;

    // Re-render calendar to show selection
    if (rf.selectedEvent) {
        await rfRenderEventCalendar(rf.selectedEvent.eventId);
    }

    // Load event slots for this date
    document.getElementById('rf-slot-section').classList.remove('d-none');
    document.getElementById('rf-slot-grid').innerHTML = '<div class="text-center text-muted py-3">' + (T.loading || 'Loading...') + '</div>';

    var res = await rfRpc('/rental-flow/api/slots', {
        product_id: rf.productId,
        date_str: ds,
        quantity: rf.quantity,
        item_role: 'event_ticket',
        event_id: rf.selectedEvent ? rf.selectedEvent.eventId : null,
    });
    rf.slots = res.slots;
    rf.selectedSlot = null;

    var el = document.getElementById('rf-slot-grid');
    el.innerHTML = '';
    if (!rf.slots.length) {
        el.innerHTML = '<p class="text-muted">' + (T.no_slots_date || 'No slots available on this date.') + '</p>';
        return;
    }
    rf.slots.forEach(function(s, i) {
        var sel = s.selectable !== false;
        var cls = 'rf-slot ' + (sel?'':'unavailable') + (rf.selectedSlot===i?' selected':'');
        var style = 'background:'+(sel?'#28a745':'#dc3545')+';';
        if (!sel) style += 'opacity:0.4;';
        var label = (s.start_display||'') + (s.end_display?' - '+s.end_display:'');
        var avail = s.seats_available !== undefined ? s.seats_available + ' ' + (T.seats || 'seats') :
                    (s.available_qty !== undefined ? s.available_qty + ' ' + (T.available || 'available') : '');
        el.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (sel?' onclick="rfSelectEventSlot('+i+')"':'') + '>' +
            '<strong>'+escH(label)+'</strong><br/>' +
            '<small>'+escH(rf.selectedEvent.price.toFixed(2)+' '+rf.currency)+'</small><br/>' +
            (avail?'<small>'+avail+'</small>':'') +
            '</div>';
    });

    // Auto-select first selectable slot, or hide add button
    var foundSelectable = false;
    for (var j=0;j<rf.slots.length;j++) {
        if (rf.slots[j].selectable !== false) {
            rfSelectEventSlot(j);
            foundSelectable = true;
            break;
        }
    }
    if (!foundSelectable) {
        rf.selectedSlot = null;
        document.getElementById('rf-add-section').classList.add('d-none');
        var maxAvail = 0;
        rf.slots.forEach(function(s) {
            var a = s.seats_available !== undefined ? s.seats_available : (s.available_qty || 0);
            if (a > maxAvail) maxAvail = a;
        });
        rfShowAvailWarning(maxAvail);
    } else {
        rfHideAvailWarning();
    }
}

function rfSelectEventSlot(i) {
    rf.selectedSlot = i;
    var s = rf.slots[i];
    rfHideAvailWarning();
    document.querySelectorAll('.rf-slot').forEach(function(el, idx) {
        el.classList.toggle('selected', idx === i);
    });
    document.getElementById('rf-add-section').classList.remove('d-none');
    rfUpdateAddPrice(rf.selectedEvent.price * rf.quantity);
}

// Override calNav for event mode
var _origCalNav = rfCalNav;
rfCalNav = function(delta) {
    rf.calendarMonth = new Date(rf.calendarMonth.getFullYear(), rf.calendarMonth.getMonth()+delta, 1);
    rf.selectedDate = null;
    if (rf.selectedEvent) {
        rfRenderEventCalendar(rf.selectedEvent.eventId);
    } else {
        rfRenderCalendar();
    }
};

// Add to basket
async function rfAddToBasket() {
    var params = {product_id: rf.productId, item_role: rf.itemRole, quantity: rf.quantity};
    if (rf.itemRole==='rental' && rf.selectedSlot!==null) {
        var s = rf.slots[rf.selectedSlot];
        params.start_datetime = s.start_datetime;
        params.end_datetime = s.end_datetime;
        params.price_unit = s.price_unit_excl || s.price_unit;
    } else if (rf.itemRole==='event_ticket' && rf.selectedEvent) {
        params.event_id = rf.selectedEvent.eventId;
        params.event_ticket_id = rf.selectedEvent.ticketId;
        params.price_unit = rf.selectedEvent.priceExcl || rf.selectedEvent.price;
        // Pass event_slot_id if a slot was selected
        if (rf.selectedSlot !== null && rf.slots[rf.selectedSlot] && rf.slots[rf.selectedSlot].event_slot_id) {
            params.event_slot_id = rf.slots[rf.selectedSlot].event_slot_id;
        }
    } else {
        params.price_unit = rf.listPrice;
    }
    try {
        var res = await rfRpc('/rental-flow/api/add-to-basket', params);
        if (res.ok) window.location.href = '/rental-flow/basket';
    } catch(e) {
        document.getElementById('rf-msg').textContent = (T.error_prefix || 'Error: ') + e.message;
    }
}

// Basket actions (used on basket page)
async function rfRemoveItem(itemId) {
    await rfRpc('/rental-flow/api/remove-from-basket', {item_id: itemId});
    window.location.reload();
}
async function rfUpdateQty(itemId, qty) {
    await rfRpc('/rental-flow/api/update-qty', {item_id: itemId, quantity: qty});
    window.location.reload();
}

function escH(s) { if(!s)return''; var d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
