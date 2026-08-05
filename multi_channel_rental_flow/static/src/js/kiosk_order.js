/**
 * Kiosk Order Flow — client-side logic.
 *
 * All pricing is computed server-side. JS only handles UI state,
 * API calls, and printing.
 *
 * Globals set by template: PROFILE_ID, PRINTER_CONFIG, CSRF_TOKEN, CURRENT_LANG, TRANSLATIONS
 */

// Convert Odoo locale (fr_FR) to JS locale (fr-FR)
var JS_LANG = (typeof CURRENT_LANG !== 'undefined' && CURRENT_LANG) ? CURRENT_LANG.replace('_', '-') : 'en';

var state = {
    dossierId: null,
    dossierName: '',
    products: [],
    categories: [],
    currentCategory: null,
    selectedProduct: null,
    quantity: 1,
    durations: [],
    selectedDuration: null,
    calendarMonth: new Date(),
    dayStates: {},
    selectedDate: null,
    slots: [],
    selectedSlot: null,
    basketItems: [],
    basketSubtotal: 0,
    basketTax: 0,
    basketTotal: 0,
    currency: '',
};

// =====================================================================
// JSON-RPC
// =====================================================================
async function rpc(url, params) {
    // Always include the selected language so API endpoints can set context
    if (typeof CURRENT_LANG !== 'undefined' && CURRENT_LANG) {
        params = Object.assign({lang: CURRENT_LANG}, params);
    }
    var resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({jsonrpc: '2.0', method: 'call', id: 1, params: params}),
    });
    var data = await resp.json();
    if (data.error) throw new Error(data.error.data?.message || data.error.message || 'Error');
    return data.result;
}

// =====================================================================
// Navigation
// =====================================================================
function showSection(id) {
    document.querySelectorAll('.ko-page').forEach(function(el) { el.classList.add('ko-hidden'); });
    document.getElementById(id).classList.remove('ko-hidden');
}

// =====================================================================
// Init — Start screen
// =====================================================================
async function startNewOrder() {
    showSection('page-loading');
    try {
        var res = await rpc('/rental-kiosk/api/basket/create', {profile_id: PROFILE_ID});
        state.dossierId = res.dossier_id;
        state.dossierName = res.dossier_name;
        state.currency = res.currency || '';
        state.basketItems = [];
        state.basketTotal = 0;
        updateBasketBadge();

        var catRes = await rpc('/rental-kiosk/api/categories', {profile_id: PROFILE_ID});
        state.categories = catRes.categories;
        renderCategories();

        if (state.categories.length > 0) {
            selectCategory(state.categories[0]);
        } else {
            await loadProducts(null, null);
        }
        showSection('page-browse');
    } catch (e) {
        alert((TRANSLATIONS.error_prefix || 'Error: ') + e.message);
        showSection('page-start');
    }
}

// =====================================================================
// Categories
// =====================================================================
function renderCategories() {
    var el = document.getElementById('category-bar');
    el.innerHTML = '<button class="ko-cat-btn active" onclick="selectCategory(null)">' + (TRANSLATIONS.all || 'All') + '</button>';
    state.categories.forEach(function(c) {
        el.innerHTML += '<button class="ko-cat-btn" data-cat-id="' + c.id +
            '" data-cat-type="' + c.type +
            '" onclick="selectCategory({id:' + c.id + ',type:\'' + c.type + '\',name:\'' +
            c.name.replace(/'/g, "\\'") + '\'})">' + escH(c.name) + '</button>';
    });
}

async function selectCategory(cat) {
    state.currentCategory = cat;
    document.querySelectorAll('.ko-cat-btn').forEach(function(b) { b.classList.remove('active'); });
    if (cat) {
        var btn = document.querySelector('[data-cat-id="' + cat.id + '"][data-cat-type="' + cat.type + '"]');
        if (btn) btn.classList.add('active');
    } else {
        document.querySelector('.ko-cat-btn').classList.add('active');
    }
    await loadProducts(cat ? cat.id : null, cat ? cat.type : null);
}

async function loadProducts(categoryId, categoryType) {
    var res = await rpc('/rental-kiosk/api/products', {
        profile_id: PROFILE_ID,
        category_id: categoryId,
        category_type: categoryType,
    });
    state.products = res.products;
    state.currency = res.products.length > 0 ? res.products[0].currency : '';
    renderProducts();
}

function renderProducts() {
    var el = document.getElementById('product-grid');
    el.innerHTML = '';
    state.products.forEach(function(p) {
        var imgHtml = p.image_url && p.use_image
            ? '<img class="ko-product-img" src="' + p.image_url + '" alt="' + escH(p.name) + '"/>'
            : '<div class="ko-product-img-placeholder">📦</div>';
        el.innerHTML +=
            '<div class="ko-product-card" onclick="selectProduct(' + p.id + ')">' +
            imgHtml +
            '<div class="ko-product-info">' +
            '<div class="ko-product-role">' + escH(p.item_role) + '</div>' +
            '<div class="ko-product-name">' + escH(p.name) + '</div>' +
            '<div class="ko-product-price">' +
            (p.has_from_price ? (TRANSLATIONS.from || 'from') + ' ' : '') +
            p.min_price.toFixed(2) + ' ' + escH(p.currency) + '</div>' +
            '</div></div>';
    });
    if (state.products.length === 0) {
        el.innerHTML = '<div class="ko-msg" style="grid-column:1/-1;">' + (TRANSLATIONS.no_products || 'No products available.') + '</div>';
    }
}

// =====================================================================
// Product detail
// =====================================================================
async function selectProduct(productId) {
    var p = state.products.find(function(x) { return x.id === productId; });
    if (!p) return;
    state.selectedProduct = p;
    state.quantity = 1;
    state.selectedDuration = null;
    state.selectedDate = null;
    state.selectedSlot = null;
    state.slots = [];
    updateSelectedDateDisplay();

    document.getElementById('detail-title').textContent = p.name;

    // Product image
    var imgEl = document.getElementById('detail-product-img');
    if (p.image_url && p.use_image) {
        imgEl.src = p.image_url;
        imgEl.style.display = 'block';
    } else {
        imgEl.style.display = 'none';
    }

    // Only show base price for non-timeslot products (addons/services).
    // For rental/timeslot products, the price is shown when selecting a slot.
    if (p.requires_timeslot) {
        document.getElementById('detail-price-base').textContent = '';
    } else {
        document.getElementById('detail-price-base').textContent = p.list_price.toFixed(2) + ' ' + p.currency;
    }

    // Show/hide sections based on product config
    var qtyEl = document.getElementById('detail-qty-section');
    var durEl = document.getElementById('detail-duration-section');
    var calEl = document.getElementById('detail-calendar-section');
    var slotEl = document.getElementById('detail-slot-section');
    var eventEl = document.getElementById('detail-event-section');
    var addEl = document.getElementById('detail-add-section');

    qtyEl.classList.toggle('ko-hidden', !p.allow_quantity_selection);
    durEl.classList.add('ko-hidden');
    calEl.classList.add('ko-hidden');
    slotEl.classList.add('ko-hidden');
    eventEl.classList.add('ko-hidden');
    addEl.classList.add('ko-hidden');
    koHideAvailWarning();

    updateQtyDisplay();

    if (p.item_role === 'event_ticket') {
        // Event flow: show event list first, calendar after selection
        eventEl.classList.remove('ko-hidden');
        await loadEvents(p.id);
    } else if (p.item_role === 'rental') {
        // Rental flow: duration + calendar
        if (p.requires_duration) {
            durEl.classList.remove('ko-hidden');
            await loadDurations(p.id);
        }
        if (p.requires_timeslot) {
            calEl.classList.remove('ko-hidden');
            state.calendarMonth = new Date();
            await renderCalendar();
        }
    }
    if (p.item_role === 'addon' || p.item_role === 'service') {
        // Simple add — show price and add button directly
        addEl.classList.remove('ko-hidden');
        updateAddSummary(p.list_price * state.quantity);
    }

    showSection('page-detail');
}

// =====================================================================
// Quantity
// =====================================================================
function changeQty(delta) {
    state.quantity = Math.max(1, state.quantity + delta);
    updateQtyDisplay();
    if (state.selectedProduct && (state.selectedProduct.item_role === 'addon' || state.selectedProduct.item_role === 'service')) {
        updateAddSummary(state.selectedProduct.list_price * state.quantity);
    }
    if (state.selectedProduct && state.selectedProduct.item_role === 'event_ticket' && state.selectedProduct._eventId) {
        // Refresh event calendar with new quantity — selectEventDate
        // will show/hide add button based on slot availability
        renderEventCalendar(state.selectedProduct._eventId);
        if (state.selectedDate) {
            selectEventDate(state.selectedDate);
        } else {
            document.getElementById('detail-add-section').classList.add('ko-hidden');
        }
    } else if (state.selectedDate && state.selectedProduct && state.selectedProduct.requires_timeslot) {
        // Rental: reload slots and calendar
        loadSlots();
        renderCalendar();
    }
    if (state.selectedSlot !== null && state.selectedProduct && state.selectedProduct.item_role !== 'event_ticket') updateSlotSelection();
}
function updateQtyDisplay() {
    document.getElementById('qty-value').textContent = state.quantity;
}

// =====================================================================
// Durations
// =====================================================================
async function loadDurations(productId) {
    var res = await rpc('/rental-kiosk/api/durations', {
        profile_id: PROFILE_ID,
        product_id: productId,
    });
    state.durations = res.durations;
    renderDurations();
}

function renderDurations() {
    var el = document.getElementById('duration-list');
    el.innerHTML = '';
    state.durations.forEach(function(d, i) {
        el.innerHTML += '<button class="ko-dur-btn' + (i === 0 ? ' active' : '') +
            '" onclick="selectDuration(' + i + ')">' + escH(d.label) + '</button>';
    });
    if (state.durations.length > 0) selectDuration(0);
}

function selectDuration(index) {
    state.selectedDuration = state.durations[index];
    document.querySelectorAll('.ko-dur-btn').forEach(function(b, i) {
        b.classList.toggle('active', i === index);
    });
    // Refresh calendar (day states depend on duration) and slots
    renderCalendar();
    if (state.selectedDate) loadSlots();
}

// =====================================================================
// Calendar
// =====================================================================
async function renderCalendar() {
    var month = state.calendarMonth;
    document.getElementById('cal-month-label').textContent =
        month.toLocaleString(JS_LANG, {month: 'long', year: 'numeric'});

    var centerStr = month.getFullYear() + '-' +
        String(month.getMonth() + 1).padStart(2, '0') + '-15';

    var res = await rpc('/rental-kiosk/api/day-states', {
        profile_id: PROFILE_ID,
        product_id: state.selectedProduct.id,
        center_date_str: centerStr,
        duration_value: state.selectedDuration ? state.selectedDuration.value : null,
        duration_unit: state.selectedDuration ? state.selectedDuration.unit : null,
        quantity: state.quantity,
        item_role: state.selectedProduct.item_role,
    });

    state.dayStates = {};
    res.days.forEach(function(d) { state.dayStates[d.date] = d; });

    var grid = document.getElementById('cal-grid');
    grid.innerHTML = '';

    // Day headers
    [TRANSLATIONS.mon||'Mon', TRANSLATIONS.tue||'Tue', TRANSLATIONS.wed||'Wed', TRANSLATIONS.thu||'Thu', TRANSLATIONS.fri||'Fri', TRANSLATIONS.sat||'Sat', TRANSLATIONS.sun||'Sun'].forEach(function(d) {
        grid.innerHTML += '<div style="text-align:center;font-size:0.8rem;color:var(--ko-muted);">' + d + '</div>';
    });

    // First day of month
    var first = new Date(month.getFullYear(), month.getMonth(), 1);
    var dow = (first.getDay() + 6) % 7; // Monday = 0
    for (var i = 0; i < dow; i++) grid.innerHTML += '<div></div>';

    var daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    for (var d = 1; d <= daysInMonth; d++) {
        var ds = month.getFullYear() + '-' +
            String(month.getMonth() + 1).padStart(2, '0') + '-' +
            String(d).padStart(2, '0');
        var info = state.dayStates[ds];
        var cls = 'ko-cal-day ';
        var clickable = false;
        if (!info || info.day_state === 'closed') {
            cls += 'closed';
        } else if (info.day_state === 'unavailable') {
            cls += 'unavailable';
        } else if (info.day_state === 'partial') {
            cls += 'available'; clickable = true;
        } else {
            cls += 'available'; clickable = true;
        }
        if (state.selectedDate === ds) cls += ' selected';
        var style = info && info.color_code ? 'background:' + info.color_code + ';' : '';
        if (info && (info.day_state === 'available' || info.day_state === 'partial')) {
            style = 'background:' + (info.color_code || 'var(--ko-success)') + ';color:#fff;';
        }
        grid.innerHTML += '<div class="' + cls + '" style="' + style + '"' +
            (clickable ? ' onclick="selectDate(\'' + ds + '\')"' : '') + '>' +
            '<div class="ko-cal-day-num">' + d + '</div>' +
            '</div>';
    }
}

function calNav(delta) {
    state.calendarMonth = new Date(
        state.calendarMonth.getFullYear(),
        state.calendarMonth.getMonth() + delta, 1
    );
    state.selectedDate = null;
    if (state.selectedProduct && state.selectedProduct._eventId) {
        renderEventCalendar(state.selectedProduct._eventId);
    } else {
        renderCalendar();
    }
}

async function selectDate(ds) {
    state.selectedDate = ds;
    updateSelectedDateDisplay();
    renderCalendar();
    await loadSlots();
}

function updateSelectedDateDisplay() {
    var display = '';
    if (state.selectedDate) {
        var d = new Date(state.selectedDate + 'T00:00:00');
        display = d.toLocaleDateString(JS_LANG, {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        });
    }
    var calDisplay = document.getElementById('selected-date-display');
    var slotDisplay = document.getElementById('slot-date-display');
    if (calDisplay) calDisplay.textContent = display ? (TRANSLATIONS.selected || 'Selected: ') + display : '';
    if (slotDisplay) slotDisplay.textContent = display || '';
}

// =====================================================================
// Slots
// =====================================================================
async function loadSlots() {
    if (!state.selectedDate) return;
    document.getElementById('detail-slot-section').classList.remove('ko-hidden');
    document.getElementById('slot-grid').innerHTML = '<div class="ko-msg"><span class="ko-spinner"></span></div>';

    var res = await rpc('/rental-kiosk/api/slots', {
        profile_id: PROFILE_ID,
        product_id: state.selectedProduct.id,
        date_str: state.selectedDate,
        duration_value: state.selectedDuration ? state.selectedDuration.value : null,
        duration_unit: state.selectedDuration ? state.selectedDuration.unit : null,
        quantity: state.quantity,
        item_role: state.selectedProduct.item_role,
    });
    state.slots = res.slots;
    state.selectedSlot = null;
    renderSlots();
}

function renderSlots() {
    var el = document.getElementById('slot-grid');
    el.innerHTML = '';
    if (state.slots.length === 0) {
        el.innerHTML = '<div class="ko-msg" style="grid-column:1/-1;">' + (TRANSLATIONS.no_slots || 'No slots available.') + '</div>';
        return;
    }
    state.slots.forEach(function(s, i) {
        var sel = s.selectable !== false;
        var cls = 'ko-slot ' + (sel ? 'selectable' : 'unavailable');
        if (state.selectedSlot === i) cls += ' selected';
        var style = 'background:' + (s.color_code || '#555') + ';color:#fff;';
        if (!sel) style += 'opacity:0.4;';
        el.innerHTML += '<div class="' + cls + '" style="' + style + '"' +
            (sel ? ' onclick="selectSlot(' + i + ')"' : '') + '>' +
            '<div class="ko-slot-time">' + escH(s.start_display || '') + '</div>' +
            '<div class="ko-slot-price">' + (s.price_unit || 0).toFixed(2) + ' ' + escH(state.currency) + '</div>' +
            (s.available_qty !== undefined ? '<div class="ko-slot-avail">' + s.available_qty + ' ' + (TRANSLATIONS.available || 'available') + '</div>' : '') +
            '</div>';
    });
}

function selectSlot(index) {
    state.selectedSlot = index;
    renderSlots();
    updateSlotSelection();
}

function updateSlotSelection() {
    var s = state.slots[state.selectedSlot];
    if (!s || s.selectable === false) {
        document.getElementById('detail-add-section').classList.add('ko-hidden');
        var avail = s ? (s.available_qty || s.seats_available || 0) : 0;
        koShowAvailWarning(avail);
        state.selectedSlot = null;
        return;
    }
    koHideAvailWarning();
    document.getElementById('detail-add-section').classList.remove('ko-hidden');
    updateAddSummary(s.price_unit * state.quantity);
}

function koShowAvailWarning(available) {
    var el = document.getElementById('ko-avail-warning');
    var txt = document.getElementById('ko-avail-warning-text');
    if (el) {
        txt.textContent = ' ' + (TRANSLATIONS.avail_only||'Only') + ' ' + available + ' ' + (TRANSLATIONS.avail_available_for||'available for the selected timeslot, but') + ' ' + state.quantity + ' ' + (TRANSLATIONS.avail_requested||'requested.');
        el.classList.remove('ko-hidden');
    }
}
function koHideAvailWarning() {
    var el = document.getElementById('ko-avail-warning');
    if (el) el.classList.add('ko-hidden');
}

function updateAddSummary(total) {
    document.getElementById('add-summary-price').textContent =
        total.toFixed(2) + ' ' + escH(state.currency || '');
}

// =====================================================================
// Events
// =====================================================================
async function loadEvents(productId) {
    var res = await rpc('/rental-kiosk/api/events', {
        profile_id: PROFILE_ID,
        product_id: productId,
    });
    state.events = res.events || [];
    var el = document.getElementById('event-list');
    el.innerHTML = '';
    if (state.events.length === 0) {
        el.innerHTML = '<div class="ko-msg">' + (TRANSLATIONS.no_events || 'No events available.') + '</div>';
        return;
    }
    state.events.forEach(function(ev) {
        el.innerHTML +=
            '<div class="ko-product-card" style="padding:16px;cursor:pointer;" ' +
            'onclick="selectEvent(' + ev.event_id + ',' + ev.ticket_id + ',' + ev.price + ',' + (ev.price_excl||ev.price) + ')">' +
            '<div class="ko-product-name">' + escH(ev.event_name) + '</div>' +
            '<div class="ko-product-role">' + escH(ev.ticket_name) + '</div>' +
            '<div class="ko-product-price">' + ev.price.toFixed(2) + ' ' + escH(state.currency) + '</div>' +
            '</div>';
    });

    // Auto-select the event with the lowest price
    if (state.events.length > 0) {
        var cheapest = state.events.reduce(function(a, b) {
            return (a.price_excl || a.price) < (b.price_excl || b.price) ? a : b;
        });
        selectEvent(cheapest.event_id, cheapest.ticket_id, cheapest.price, cheapest.price_excl || cheapest.price);
    }
}

async function selectEvent(eventId, ticketId, priceIncl, priceExcl) {
    state.selectedProduct._eventId = eventId;
    state.selectedProduct._ticketId = ticketId;
    state.selectedProduct._eventPrice = priceIncl;
    state.selectedProduct._eventPriceExcl = priceExcl;

    // Show calendar for event dates
    document.getElementById('detail-calendar-section').classList.remove('ko-hidden');
    var ev = state.events.find(function(e) { return e.event_id === eventId; });
    if (ev && ev.date_begin) {
        var evDate = new Date(ev.date_begin);
        state.calendarMonth = new Date(evDate.getFullYear(), evDate.getMonth(), 1);
    }
    state.selectedDate = null;
    await renderEventCalendar(eventId);
}

async function renderEventCalendar(eventId) {
    var month = state.calendarMonth;
    document.getElementById('cal-month-label').textContent =
        month.toLocaleString(JS_LANG, {month:'long', year:'numeric'});

    var centerStr = month.getFullYear() + '-' +
        String(month.getMonth()+1).padStart(2,'0') + '-15';
    var res = await rpc('/rental-kiosk/api/day-states', {
        profile_id: PROFILE_ID,
        product_id: state.selectedProduct.id,
        center_date_str: centerStr,
        quantity: state.quantity,
        item_role: 'event_ticket',
        event_id: eventId,
    });
    state.dayStates = {};
    res.days.forEach(function(d) { state.dayStates[d.date] = d; });

    var grid = document.getElementById('cal-grid');
    grid.innerHTML = '';
    [TRANSLATIONS.mon||'Mon', TRANSLATIONS.tue||'Tue', TRANSLATIONS.wed||'Wed', TRANSLATIONS.thu||'Thu', TRANSLATIONS.fri||'Fri', TRANSLATIONS.sat||'Sat', TRANSLATIONS.sun||'Sun'].forEach(function(d) {
        grid.innerHTML += '<div style="text-align:center;font-size:0.8rem;color:var(--ko-muted);">'+d+'</div>';
    });
    var first = new Date(month.getFullYear(), month.getMonth(), 1);
    var dow = (first.getDay()+6)%7;
    for (var i=0;i<dow;i++) grid.innerHTML += '<div></div>';
    var daysInMonth = new Date(month.getFullYear(), month.getMonth()+1, 0).getDate();
    var firstAvailable = null;
    for (var d=1;d<=daysInMonth;d++) {
        var ds = month.getFullYear()+'-'+String(month.getMonth()+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
        var info = state.dayStates[ds];
        var cls = 'ko-cal-day ';
        var clickable = false;
        var style = '';
        if (!info || info.day_state==='closed') {
            style = 'background:#555;color:#999;cursor:not-allowed;';
        } else if (info.day_state==='unavailable' || info.available_slot_count===0) {
            style = 'background:var(--ko-danger);color:#fff;cursor:not-allowed;';
        } else {
            style = 'background:'+(info.color_code||'var(--ko-success)')+';color:#fff;';
            clickable = true;
            if (!firstAvailable) firstAvailable = ds;
        }
        if (state.selectedDate===ds) cls += ' selected';
        grid.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (clickable?' onclick="selectEventDate(\''+ds+'\')"':'') +
            '><div class="ko-cal-day-num">'+d+'</div></div>';
    }

    // Auto-select first available
    if (firstAvailable && !state.selectedDate) {
        selectEventDate(firstAvailable);
    }
}

async function selectEventDate(ds) {
    state.selectedDate = ds;
    updateSelectedDateDisplay();

    if (state.selectedProduct._eventId) {
        await renderEventCalendar(state.selectedProduct._eventId);
    }

    // Load event slots
    document.getElementById('detail-slot-section').classList.remove('ko-hidden');
    document.getElementById('slot-grid').innerHTML = '<div class="ko-msg"><span class="ko-spinner"></span></div>';

    var res = await rpc('/rental-kiosk/api/slots', {
        profile_id: PROFILE_ID,
        product_id: state.selectedProduct.id,
        date_str: ds,
        quantity: state.quantity,
        item_role: 'event_ticket',
        event_id: state.selectedProduct._eventId,
    });
    state.slots = res.slots;
    state.selectedSlot = null;

    var el = document.getElementById('slot-grid');
    el.innerHTML = '';
    if (!state.slots.length) {
        el.innerHTML = '<div class="ko-msg" style="grid-column:1/-1;">' + (TRANSLATIONS.no_slots_date || 'No slots on this date.') + '</div>';
        return;
    }
    state.slots.forEach(function(s, i) {
        var sel = s.selectable !== false;
        var cls = 'ko-slot ' + (sel?'selectable':'unavailable');
        var style = 'background:'+(sel?'var(--ko-success)':'var(--ko-danger)')+';color:#fff;';
        if (!sel) style += 'opacity:0.4;';
        var label = (s.start_display||'') + (s.end_display?' - '+s.end_display:'');
        el.innerHTML += '<div class="'+cls+'" style="'+style+'"' +
            (sel?' onclick="selectEventSlot('+i+')"':'') + '>' +
            '<div class="ko-slot-time">'+escH(label)+'</div>' +
            '<div class="ko-slot-price">'+state.selectedProduct._eventPrice.toFixed(2)+' '+escH(state.currency)+'</div>' +
            (s.seats_available!==undefined?'<div class="ko-slot-avail">'+s.seats_available+' '+(TRANSLATIONS.seats||'seats')+'</div>':'')+
            '</div>';
    });

    // Auto-select first selectable, or hide add button
    var foundSelectable = false;
    for (var j=0;j<state.slots.length;j++) {
        if (state.slots[j].selectable !== false) {
            selectEventSlot(j);
            foundSelectable = true;
            break;
        }
    }
    if (!foundSelectable) {
        state.selectedSlot = null;
        document.getElementById('detail-add-section').classList.add('ko-hidden');
        var maxAvail = 0;
        state.slots.forEach(function(s) {
            var a = s.seats_available !== undefined ? s.seats_available : (s.available_qty || 0);
            if (a > maxAvail) maxAvail = a;
        });
        koShowAvailWarning(maxAvail);
    } else {
        koHideAvailWarning();
    }
}

function selectEventSlot(i) {
    state.selectedSlot = i;
    koHideAvailWarning();
    document.querySelectorAll('.ko-slot').forEach(function(el, idx) {
        el.classList.toggle('selected', idx === i);
    });
    document.getElementById('detail-add-section').classList.remove('ko-hidden');
    updateAddSummary(state.selectedProduct._eventPrice * state.quantity);
}

// =====================================================================
// Add to basket
// =====================================================================
async function addToBasket() {
    var p = state.selectedProduct;
    if (!p) return;

    var params = {
        dossier_id: state.dossierId,
        product_id: p.id,
        item_role: p.item_role,
        quantity: state.quantity,
    };

    if (p.item_role === 'rental' && state.selectedSlot !== null) {
        var s = state.slots[state.selectedSlot];
        params.start_datetime = s.start_datetime;
        params.end_datetime = s.end_datetime;
        // Store excl. tax price — basket display computes tax separately
        params.price_unit = s.price_unit_excl || s.price_unit;
    } else if (p.item_role === 'event_ticket' && p._eventId) {
        params.event_id = p._eventId;
        params.event_ticket_id = p._ticketId;
        params.price_unit = p._eventPriceExcl || p._eventPrice || p.list_price;
        if (state.selectedSlot !== null && state.slots[state.selectedSlot] && state.slots[state.selectedSlot].event_slot_id) {
            params.event_slot_id = state.slots[state.selectedSlot].event_slot_id;
        }
    } else {
        params.price_unit = p.list_price;
    }

    await rpc('/rental-kiosk/api/basket/add', params);
    await refreshBasket();
    showSection('page-browse');
}

// =====================================================================
// Basket
// =====================================================================
async function refreshBasket() {
    var res = await rpc('/rental-kiosk/api/basket/get', {dossier_id: state.dossierId});
    state.basketItems = res.items;
    state.basketSubtotal = res.subtotal || res.total;
    state.basketTax = res.tax || 0;
    state.basketTotal = res.total;
    state.currency = res.currency;
    updateBasketBadge();
}

function updateBasketBadge() {
    var badge = document.getElementById('basket-badge');
    var count = state.basketItems.length;
    badge.textContent = count;
    badge.style.display = count > 0 ? 'flex' : 'none';
    // Show/hide checkout button in top bar
    var checkoutBtn = document.getElementById('topbar-checkout-btn');
    if (checkoutBtn) {
        checkoutBtn.style.display = count > 0 ? 'block' : 'none';
    }
}

async function showBasket() {
    await refreshBasket();
    var el = document.getElementById('basket-items');
    el.innerHTML = '';
    if (state.basketItems.length === 0) {
        el.innerHTML = '<div class="ko-msg">' + (TRANSLATIONS.basket_empty || 'Your basket is empty.') + '</div>';
    }
    state.basketItems.forEach(function(item) {
        el.innerHTML +=
            '<div class="ko-basket-item">' +
            '<div class="ko-basket-item-info">' +
            '<div class="ko-basket-item-name">' + escH(item.product_name) + '</div>' +
            '<div class="ko-basket-item-detail">' +
            escH(item.item_role) +
            (item.slot_name ? ' — ' + escH(item.slot_name) : '') +
            (item.event_name ? ' — ' + escH(item.event_name) : '') +
            '</div></div>' +
            '<div style="display:flex; align-items:center; gap:8px;">' +
            '<button class="ko-qty-btn" style="width:36px;height:36px;font-size:1.2rem;" ' +
            'onclick="changeBasketQty(' + item.id + ',-1)">−</button>' +
            '<span style="font-size:1.1rem;font-weight:600;min-width:28px;text-align:center;">' + item.quantity + '</span>' +
            '<button class="ko-qty-btn" style="width:36px;height:36px;font-size:1.2rem;" ' +
            'onclick="changeBasketQty(' + item.id + ',1)">+</button>' +
            '</div>' +
            '<div class="ko-basket-item-price">' + item.price_subtotal.toFixed(2) + ' ' + escH(state.currency) + '</div>' +
            '<button class="ko-basket-remove" onclick="removeItem(' + item.id + ')">×</button>' +
            '</div>';
    });
    var totalHtml = '';
    if (state.basketTax > 0) {
        totalHtml = (TRANSLATIONS.subtotal||'Subtotal') + ': ' + state.basketSubtotal.toFixed(2) + ' ' + escH(state.currency) +
            '<br/>' + (TRANSLATIONS.tax||'Tax') + ': ' + state.basketTax.toFixed(2) + ' ' + escH(state.currency) +
            '<br/><strong>' + (TRANSLATIONS.total||'Total') + ': ' + state.basketTotal.toFixed(2) + ' ' + escH(state.currency) + '</strong>';
    } else {
        totalHtml = (TRANSLATIONS.total||'Total') + ': ' + state.basketTotal.toFixed(2) + ' ' + escH(state.currency);
    }
    document.getElementById('basket-total').innerHTML = totalHtml;
    showSection('page-basket');
}

async function changeBasketQty(itemId, delta) {
    var item = state.basketItems.find(function(i) { return i.id === itemId; });
    if (!item) return;
    var newQty = item.quantity + delta;
    if (newQty <= 0) {
        await removeItem(itemId);
        return;
    }
    await rpc('/rental-kiosk/api/basket/update-qty', {
        dossier_id: state.dossierId,
        item_id: itemId,
        quantity: newQty,
    });
    await showBasket();
}

async function removeItem(itemId) {
    await rpc('/rental-kiosk/api/basket/remove', {
        dossier_id: state.dossierId,
        item_id: itemId,
    });
    await showBasket();
}

// =====================================================================
// Customer info screen (before checkout)
// =====================================================================
function showCustomerInfo() {
    if (state.basketItems.length === 0) return;
    document.getElementById('ci-email').value = '';
    document.getElementById('ci-name').value = '';
    document.getElementById('ci-msg').textContent = '';
    showSection('page-customer-info');
}

async function submitCustomerInfo() {
    var email = document.getElementById('ci-email').value.trim();
    var name = document.getElementById('ci-name').value.trim();
    var msgEl = document.getElementById('ci-msg');

    if (!email) {
        msgEl.textContent = TRANSLATIONS.email_required || 'Email address is required.';
        return;
    }
    if (!email.includes('@')) {
        msgEl.textContent = TRANSLATIONS.invalid_email || 'Please enter a valid email address.';
        return;
    }

    // Save customer info to dossier
    try {
        await rpc('/rental-kiosk/api/basket/set-customer', {
            dossier_id: state.dossierId,
            email: email,
            name: name,
        });
    } catch (e) {
        msgEl.textContent = (TRANSLATIONS.error_prefix || 'Error: ') + e.message;
        return;
    }

    // Proceed to checkout
    await doCheckout();
}

// =====================================================================
// Checkout
// =====================================================================
async function doCheckout() {
    if (state.basketItems.length === 0) return;
    showSection('page-loading');
    document.getElementById('loading-msg').textContent = TRANSLATIONS.processing_payment || 'Processing payment...';

    try {
        var res = await rpc('/rental-kiosk/api/checkout', {dossier_id: state.dossierId});

        if (!res.ok) {
            document.getElementById('error-msg').textContent = res.message || (TRANSLATIONS.payment_failed || 'Payment failed.');
            showSection('page-error');
            return;
        }

        // Success — clear basket state and print tickets
        state.basketItems = [];
        state.basketSubtotal = 0;
        state.basketTax = 0;
        state.basketTotal = 0;
        state.dossierId = null;
        updateBasketBadge();

        document.getElementById('success-dossier').textContent = res.dossier_name;
        var successTotal = res.amount_total.toFixed(2) + ' ' + res.currency;
        if (res.amount_tax) {
            successTotal = 'Subtotal: ' + res.amount_untaxed.toFixed(2) + ' ' + res.currency +
                ' | Tax: ' + res.amount_tax.toFixed(2) + ' ' + res.currency +
                ' | Total: ' + res.amount_total.toFixed(2) + ' ' + res.currency;
        }
        document.getElementById('success-total').textContent = successTotal;
        document.getElementById('success-count').textContent = res.ticket_count + ' ' + (TRANSLATIONS.ticket_count || 'ticket(s)');
        showSection('page-success');

        // Auto-print
        if (PRINTER_CONFIG.mode !== 'none' && res.tickets && res.tickets.length > 0) {
            await autoPrintTickets(res);
        }
    } catch (e) {
        document.getElementById('error-msg').textContent = (TRANSLATIONS.error_prefix || 'Error: ') + e.message;
        showSection('page-error');
    }
}

async function autoPrintTickets(payload) {
    var printMsg = document.getElementById('success-print-msg');

    // Step 1: Print receipt (sales summary)
    if (PRINTER_CONFIG.epos_receipt_template) {
        printMsg.textContent = TRANSLATIONS.printing_receipt || 'Printing receipt...';
        try {
            var receiptXml = buildReceiptXml(payload);
            if (PRINTER_CONFIG.mode === 'pos_epos_ip' && PRINTER_CONFIG.printer_ip) {
                await sendEposXml(receiptXml);
            } else if (PRINTER_CONFIG.mode === 'browser') {
                printBrowser(payload);
            }
        } catch (e) {
            printMsg.textContent = (TRANSLATIONS.receipt_print_error || 'Receipt print error: ') + e.message;
            printMsg.style.color = 'var(--ko-danger)';
        }
    }

    // Step 2: Print tickets
    printMsg.textContent = TRANSLATIONS.printing_tickets || 'Printing tickets...';
    try {
        if (PRINTER_CONFIG.mode === 'pos_epos_ip' && PRINTER_CONFIG.printer_ip) {
            await printEpson(payload);
        } else if (PRINTER_CONFIG.mode === 'browser') {
            printBrowser(payload);
        }
        printMsg.textContent = TRANSLATIONS.receipt_tickets_printed || 'Receipt and tickets printed!';
        printMsg.style.color = 'var(--ko-success)';

        await rpc('/rental-kiosk/mark-printed', {
            profile_id: PROFILE_ID,
            identifier: payload.dossier_name,
            email: '',
        });
    } catch (e) {
        printMsg.textContent = (TRANSLATIONS.ticket_print_error || 'Ticket print error: ') + e.message;
        printMsg.style.color = 'var(--ko-danger)';
    }
}

/**
 * Build ePOS XML for the sales receipt using the receipt template.
 * Uses the same templateToEpos engine as tickets, with {{ITEMS}} support.
 */
function buildReceiptXml(payload) {
    var tpl = PRINTER_CONFIG.epos_receipt_template || '';
    if (!tpl) return '';

    var cur = payload.currency || '';
    var vars = {
        'dossier_name': payload.dossier_name || '',
        'customer': payload.customer || '',
        'email': payload.email || '',
        'subtotal': (payload.amount_untaxed || 0).toFixed(2) + ' ' + cur,
        'tax': (payload.amount_tax || 0).toFixed(2) + ' ' + cur,
        'total': (payload.amount_total || 0).toFixed(2) + ' ' + cur,
        'payment_ref': payload.payment_reference || '',
        '_items': payload.tickets || [],
        '_tax_lines': payload.tax_lines || [],
        '_currency': cur,
    };

    // templateToEpos is defined in kiosk_ticket_lookup.js
    var cmds = '';
    if (typeof templateToEpos === 'function') {
        cmds = templateToEpos(tpl, vars);
    }

    return '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
         + '<s:Body>'
         + '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'
         + cmds
         + '</epos-print>'
         + '</s:Body>'
         + '</s:Envelope>';
}

/**
 * Send raw ePOS XML to the printer (shared by receipt + tickets).
 */
async function sendEposXml(xml) {
    if (!xml) return;
    var ip = PRINTER_CONFIG.printer_ip;
    var url = window.location.protocol + '//' + ip + '/cgi-bin/epos/service.cgi?devid=local_printer';
    var resp = await fetch(url, {method: 'POST', body: xml, signal: AbortSignal.timeout(15000)});
    var body = await resp.text();
    var parsed = new DOMParser().parseFromString(body, 'application/xml');
    var response = parsed.querySelector('response');
    if (!response || response.getAttribute('success') !== 'true') {
        throw new Error('Printer error: ' + (response ? response.getAttribute('code') : 'no response'));
    }
}

// =====================================================================
// Print functions — reused from kiosk_ticket_lookup.js pattern
// =====================================================================
async function printEpson(payload) {
    var ip = PRINTER_CONFIG.printer_ip;
    var url = window.location.protocol + '//' + ip + '/cgi-bin/epos/service.cgi?devid=local_printer';
    var xml = buildEpsonXmlFromTemplate(payload);
    var resp = await fetch(url, {method: 'POST', body: xml, signal: AbortSignal.timeout(15000)});
    var body = await resp.text();
    var parsed = new DOMParser().parseFromString(body, 'application/xml');
    var response = parsed.querySelector('response');
    if (!response || response.getAttribute('success') !== 'true') {
        throw new Error('Printer error: ' + (response ? response.getAttribute('code') : 'no response'));
    }
}

function buildEpsonXmlFromTemplate(payload) {
    // Use the template engine from kiosk_ticket_lookup.js if available,
    // otherwise use a simple fallback
    if (typeof buildEpsonXml === 'function') {
        return buildEpsonXml(payload);
    }
    // Simple fallback
    var cmds = '<text align="center" dw="true" dh="true">TICKETS</text><feed line="2"/>';
    cmds += '<text>' + escX(payload.dossier_name || '') + '</text><feed line="2"/>';
    (payload.tickets || []).forEach(function(t) {
        cmds += '<text align="left" dw="true">#' + t.sequence + ' ' + escX(t.print_title || '') + '</text><feed line="1"/>';
        cmds += '<text>' + escX(t.order_name || '') + '</text><feed line="2"/>';
    });
    cmds += '<text align="center">Total: ' + (payload.amount_total || 0) + ' ' + escX(payload.currency || '') + '</text>';
    cmds += '<feed line="3"/><cut type="feed"/>';
    return '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>' +
        '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">' +
        cmds + '</epos-print></s:Body></s:Envelope>';
}

function printBrowser(payload) {
    var h = '<html><body style="font-family:monospace;font-size:12px;"><h2>TICKETS</h2>';
    h += '<p>' + escH(payload.dossier_name || '') + '</p><hr/>';
    (payload.tickets || []).forEach(function(t) {
        h += '<p><strong>#' + t.sequence + ' ' + escH(t.print_title || '') + '</strong><br/>';
        h += escH(t.order_name || '') + '</p><hr/>';
    });
    h += '<p>Total: ' + (payload.amount_total || 0) + ' ' + escH(payload.currency || '') + '</p></body></html>';
    var w = window.open('', '_blank');
    w.document.write(h);
    w.document.close();
    w.print();
}

function newOrder() { showSection('page-start'); }
function backToBrowse() { showSection('page-browse'); }

// =====================================================================
// Helpers
// =====================================================================
function escH(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function escX(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
