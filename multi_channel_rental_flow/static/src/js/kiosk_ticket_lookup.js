/**
 * Kiosk Ticket Lookup — client-side logic.
 *
 * Handles lookup, display and printing of dossier tickets.
 * Printing uses the same Epson ePOS approach as Odoo POS:
 * SOAP envelope with proper namespace, protocol matching the page.
 *
 * Global variables set by the QWeb template:
 *   PROFILE_ID, PRINTER_CONFIG, CSRF_TOKEN
 */

var currentPayload = null;
var currentIdentifier = '';
var currentEmail = '';

// =====================================================================
// JSON-RPC helper
// =====================================================================

async function jsonRpc(url, params) {
    var resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            jsonrpc: '2.0', method: 'call', id: 1,
            params: params,
        }),
    });
    var data = await resp.json();
    if (data.error) {
        throw new Error(data.error.data?.message || data.error.message || 'Unknown error');
    }
    return data.result;
}

// =====================================================================
// Lookup
// =====================================================================

async function doLookup() {
    var identifier = document.getElementById('input-identifier').value.trim();
    var email = document.getElementById('input-email').value.trim();
    var msgEl = document.getElementById('lookup-message');
    var btn = document.getElementById('btn-lookup');

    if (!identifier || !email) {
        msgEl.className = 'kiosk-message kiosk-error';
        msgEl.textContent = TRANSLATIONS.please_enter_both || 'Please enter both fields.';
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="kiosk-spinner"></span>';
    msgEl.textContent = '';

    try {
        var result = await jsonRpc('/rental-kiosk/lookup', {
            profile_id: PROFILE_ID,
            identifier: identifier,
            email: email,
        });

        if (!result.ok) {
            msgEl.className = 'kiosk-message kiosk-error';
            msgEl.textContent = result.message || (TRANSLATIONS.not_found || 'Not found.');
            btn.disabled = false;
            btn.textContent = TRANSLATIONS.look_up || 'Look Up';
            return;
        }

        currentPayload = result;
        currentIdentifier = identifier;
        currentEmail = email;
        showResults(result);
    } catch (e) {
        msgEl.className = 'kiosk-message kiosk-error';
        msgEl.textContent = (TRANSLATIONS.error_prefix || 'Error: ') + e.message;
    }

    btn.disabled = false;
    btn.textContent = TRANSLATIONS.look_up || 'Look Up';
}

// =====================================================================
// Display results
// =====================================================================

function showResults(payload) {
    document.getElementById('lookup-section').classList.add('kiosk-hidden');
    document.getElementById('results-section').classList.remove('kiosk-hidden');

    var summary = document.getElementById('dossier-summary');
    summary.innerHTML =
        '<div class="kiosk-ticket-title">' + escHtml(payload.dossier_name) +
        (payload.dossier_description ? ' — ' + escHtml(payload.dossier_description) : '') +
        '</div>' +
        '<div class="kiosk-ticket-detail">' +
        (TRANSLATIONS.customer || 'Customer') + ': ' + escHtml(payload.customer) + '<br/>' +
        (TRANSLATIONS.tickets || 'Tickets') + ': ' + payload.ticket_count + '<br/>' +
        (TRANSLATIONS.total || 'Total') + ': ' + payload.amount_total + ' ' + escHtml(payload.currency) +
        '</div>';

    if (payload.already_printed) {
        summary.innerHTML += '<div class="mt-2" style="color:#ffc107;">' + (TRANSLATIONS.already_printed || 'Tickets have already been printed.') + '</div>';
    }

    var list = document.getElementById('ticket-list');
    list.innerHTML = '';
    (payload.tickets || []).forEach(function(t) {
        var detail = '';
        if (t.ticket_type === 'event') {
            detail = (TRANSLATIONS.event || 'Event') + ': ' + escHtml(t.event_name);
            if (t.event_slot) detail += ' (' + escHtml(t.event_slot) + ')';
        } else if (t.timeslot_start) {
            detail = t.timeslot_start.replace('T', ' ').substring(0, 16);
            if (t.timeslot_end) {
                detail += ' — ' + t.timeslot_end.replace('T', ' ').substring(11, 16);
            }
        }
        list.innerHTML +=
            '<div class="kiosk-ticket-card">' +
            '<span class="kiosk-ticket-badge">#' + t.sequence + '</span>' +
            '<div class="kiosk-ticket-title">' + escHtml(t.print_title) + '</div>' +
            '<div class="kiosk-ticket-detail">' +
            escHtml(t.print_subtitle) +
            (t.quantity > 1 ? ' × ' + t.quantity : '') +
            (detail ? '<br/>' + detail : '') +
            '<br/>' + escHtml(t.order_name) +
            '</div></div>';
    });
}

// =====================================================================
// Print orchestration
// =====================================================================

async function doPrint() {
    var msgEl = document.getElementById('print-message');
    var btn = document.getElementById('btn-print');
    btn.disabled = true;
    btn.innerHTML = '<span class="kiosk-spinner"></span> ' + (TRANSLATIONS.printing || 'Printing...');
    msgEl.textContent = '';

    try {
        var printed = false;

        if (PRINTER_CONFIG.mode === 'pos_epos_ip' && PRINTER_CONFIG.printer_ip) {
            printed = await printEpson(currentPayload);
        } else if (PRINTER_CONFIG.mode === 'pos_iot_box' && PRINTER_CONFIG.proxy_ip) {
            printed = await printProxy(currentPayload);
        } else if (PRINTER_CONFIG.mode === 'browser') {
            printBrowser(currentPayload);
            printed = true;
        } else {
            msgEl.className = 'kiosk-message kiosk-error';
            msgEl.textContent = TRANSLATIONS.no_printer || 'No printer configured.';
            btn.disabled = false;
            btn.textContent = TRANSLATIONS.print_tickets || 'Print Tickets';
            return;
        }

        if (printed) {
            await jsonRpc('/rental-kiosk/mark-printed', {
                profile_id: PROFILE_ID,
                identifier: currentIdentifier,
                email: currentEmail,
            });
            msgEl.className = 'kiosk-message kiosk-success';
            msgEl.textContent = TRANSLATIONS.printed_success || 'Tickets printed successfully!';
            btn.textContent = TRANSLATIONS.printed_check || 'Printed ✓';
        }
    } catch (e) {
        msgEl.className = 'kiosk-message kiosk-error';
        var errMsg = (TRANSLATIONS.print_error || 'Print error: ') + e.message;
        if (window.location.protocol === 'https:' && PRINTER_CONFIG.printer_ip) {
            errMsg += ' — ' + (TRANSLATIONS.https_warning || 'If using HTTPS, you may need to accept the printer certificate by visiting') + ' ' + window.location.protocol
                + '//' + PRINTER_CONFIG.printer_ip + ' first.';
        }
        msgEl.textContent = errMsg;
        btn.disabled = false;
        btn.textContent = TRANSLATIONS.retry_print || 'Retry Print';
    }
}

// =====================================================================
// Epson ePOS printing — same approach as Odoo POS
//
// Uses SOAP envelope with namespace:
//   http://www.epson-pos.com/schemas/2011/03/epos-print
// Protocol matches current page (HTTP/HTTPS).
// Endpoint: /cgi-bin/epos/service.cgi?devid=local_printer
// =====================================================================

async function printEpson(payload) {
    var ip = PRINTER_CONFIG.printer_ip;
    var protocol = window.location.protocol;
    var url = protocol + '//' + ip + '/cgi-bin/epos/service.cgi?devid=local_printer';

    var xml = buildEpsonXml(payload);

    var resp = await fetch(url, {
        method: 'POST',
        body: xml,
        signal: AbortSignal.timeout(15000),
    });

    var body = await resp.text();
    var parser = new DOMParser();
    var parsed = parser.parseFromString(body, 'application/xml');
    var response = parsed.querySelector('response');
    if (response && response.getAttribute('success') === 'true') {
        return true;
    }
    var code = response ? response.getAttribute('code') : 'unknown';
    throw new Error('Printer returned error code: ' + code);
}

function buildEpsonXml(payload) {
    var headerTpl = PRINTER_CONFIG.epos_ticket_header || '';
    var bodyTpl = PRINTER_CONFIG.epos_ticket_body || '';
    var footerTpl = PRINTER_CONFIG.epos_ticket_footer || '';

    // Global replacements for header/footer
    var globalVars = {
        'dossier_name': payload.dossier_name || '',
        'customer': payload.customer || '',
        'email': payload.email || '',
        'total': (payload.amount_total || '0') + ' ' + (payload.currency || ''),
        'payment_ref': payload.payment_reference || '',
    };

    var cmds = '';
    cmds += templateToEpos(headerTpl, globalVars);

    // Per-ticket body
    (payload.tickets || []).forEach(function(t) {
        var timeslotStart = t.timeslot_start ? t.timeslot_start.replace('T', ' ').substring(0, 16) : '';
        var timeslotEnd = t.timeslot_end ? t.timeslot_end.replace('T', ' ').substring(0, 16) : '';
        // For same-day rentals, show just start date + both times
        // For multi-day, show full date+time for both
        var timeslotLine = '';
        if (timeslotStart && timeslotEnd) {
            var startDate = timeslotStart.substring(0, 10);
            var endDate = timeslotEnd.substring(0, 10);
            if (startDate === endDate) {
                // Same day: "2026-07-01 10:00 - 12:00"
                timeslotLine = timeslotStart + ' - ' + timeslotEnd.substring(11, 16);
            } else {
                // Multi-day: "2026-07-01 10:00 - 2026-07-06 10:00"
                timeslotLine = timeslotStart + ' - ' + timeslotEnd;
            }
        } else if (timeslotStart) {
            timeslotLine = timeslotStart;
        }
        var ticketVars = Object.assign({}, globalVars, {
            'sequence': String(t.sequence || ''),
            'print_title': t.print_title || '',
            'print_subtitle': t.print_subtitle || '',
            'product_name': t.product_name || '',
            'order_name': t.order_name || '',
            'quantity': String(t.quantity || 1),
            'quantity_line': t.quantity > 1 ? 'x ' + t.quantity : '',
            'timeslot_start': timeslotStart,
            'timeslot_end': timeslotEnd,
            'timeslot_line': timeslotLine,
            'event_name': t.event_name || '',
            'event_line': t.event_name ? 'Event: ' + t.event_name : '',
            'event_slot': t.event_slot || '',
            'attendee_name': t.attendee_name || '',
            'registration_barcode': t.registration_barcode || '',
            'barcode_line': t.registration_barcode ? 'Code: ' + t.registration_barcode : '',
        });
        cmds += templateToEpos(bodyTpl, ticketVars);
    });

    cmds += templateToEpos(footerTpl, globalVars);

    return '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
         + '<s:Body>'
         + '<epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'
         + cmds
         + '</epos-print>'
         + '</s:Body>'
         + '</s:Envelope>';
}

/**
 * Convert a template string with {{codes}} to ePOS XML commands.
 *
 * Formatting codes:
 *   {{BOLD_ON}} / {{BOLD_OFF}}          — bold text
 *   {{ALIGN_LEFT/CENTER/RIGHT}}         — text alignment
 *   {{DOUBLE}} / {{DOUBLE_OFF}}         — double-height + double-width
 *   {{SIZE_1}} … {{SIZE_8}}             — text size 1x to 8x (height+width)
 *   {{WIDE_1}} … {{WIDE_8}}            — width only (height stays 1x)
 *   {{TALL_1}} … {{TALL_8}}            — height only (width stays 1x)
 *   {{FEED}}                            — line feed
 *   {{FEED_N}} (e.g. {{FEED_3}})       — N line feeds
 *   {{CUT}}                             — paper cut
 *   {{QR:content}}                      — QR code with literal content
 *   {{QR_field}}                        — QR code with value of a data field
 *   {{BARCODE:content}}                 — Code128 barcode with literal content
 *   {{BARCODE_field}}                   — Code128 barcode with value of a data field
 *
 * Data codes ({{dossier_name}}, etc.) are replaced with text content.
 * Empty lines (after replacement) are skipped.
 */
function templateToEpos(template, vars) {
    if (!template) return '';

    var cmds = '';
    var lines = template.split('\n');

    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;

        var parts = line.split(/(\{\{[^}]+\}\})/);
        var lineHasContent = false;

        for (var j = 0; j < parts.length; j++) {
            var part = parts[j];
            if (!part) continue;

            var m = part.match(/^\{\{(.+)\}\}$/);
            if (m) {
                var code = m[1];
                var handled = true;

                // --- Formatting codes ---
                switch (code) {
                    case 'BOLD_ON':      cmds += xmlEl('text', {em: 'true'}); break;
                    case 'BOLD_OFF':     cmds += xmlEl('text', {em: 'false'}); break;
                    case 'ALIGN_LEFT':   cmds += xmlEl('text', {align: 'left'}); break;
                    case 'ALIGN_CENTER': cmds += xmlEl('text', {align: 'center'}); break;
                    case 'ALIGN_RIGHT':  cmds += xmlEl('text', {align: 'right'}); break;
                    case 'DOUBLE':       cmds += xmlEl('text', {dw: 'true', dh: 'true'}); break;
                    case 'DOUBLE_OFF':   cmds += xmlEl('text', {dw: 'false', dh: 'false'}); break;
                    case 'FEED':         cmds += xmlEl('feed', {line: '1'}); break;
                    case 'CUT':          cmds += xmlEl('cut', {type: 'feed'}); break;
                    case 'LOGO':         cmds += buildLogo(); lineHasContent = true; break;
                    case 'LINE':         cmds += xmlEl('text', {}, '--------------------------------'); cmds += xmlEl('feed', {line:'1'}); break;
                    default:             handled = false; break;
                }

                if (handled) continue;

                // --- Text sizes: SIZE_1 to SIZE_8 (both width+height) ---
                var sizeMatch = code.match(/^SIZE_([1-8])$/);
                if (sizeMatch) {
                    var s = sizeMatch[1];
                    cmds += xmlEl('text', {width: s, height: s});
                    continue;
                }

                // --- Width only: WIDE_1 to WIDE_8 ---
                var wideMatch = code.match(/^WIDE_([1-8])$/);
                if (wideMatch) {
                    cmds += xmlEl('text', {width: wideMatch[1], height: '1'});
                    continue;
                }

                // --- Height only: TALL_1 to TALL_8 ---
                var tallMatch = code.match(/^TALL_([1-8])$/);
                if (tallMatch) {
                    cmds += xmlEl('text', {width: '1', height: tallMatch[1]});
                    continue;
                }

                // --- Multi-line feed: FEED_N ---
                var feedMatch = code.match(/^FEED_(\d+)$/);
                if (feedMatch) {
                    cmds += xmlEl('feed', {line: feedMatch[1]});
                    continue;
                }

                // --- QR code with literal: QR:content ---
                var qrLiteral = code.match(/^QR:(.+)$/);
                if (qrLiteral) {
                    var qrContent = qrLiteral[1];
                    // Replace any data vars inside the QR content
                    qrContent = qrContent.replace(/\{(\w+)\}/g, function(_, k) {
                        return vars.hasOwnProperty(k) ? vars[k] : '';
                    });
                    cmds += buildQrCode(qrContent);
                    lineHasContent = true;
                    continue;
                }

                // --- QR code from field: QR_field ---
                var qrField = code.match(/^QR_(\w+)$/);
                if (qrField) {
                    var qrVal = vars.hasOwnProperty(qrField[1]) ? vars[qrField[1]] : '';
                    if (qrVal) {
                        cmds += buildQrCode(qrVal);
                        lineHasContent = true;
                    }
                    continue;
                }

                // --- Barcode with literal: BARCODE:content ---
                var bcLiteral = code.match(/^BARCODE:(.+)$/);
                if (bcLiteral) {
                    var bcContent = bcLiteral[1];
                    bcContent = bcContent.replace(/\{(\w+)\}/g, function(_, k) {
                        return vars.hasOwnProperty(k) ? vars[k] : '';
                    });
                    cmds += buildBarcode(bcContent);
                    lineHasContent = true;
                    continue;
                }

                // --- Barcode from field: BARCODE_field ---
                var bcField = code.match(/^BARCODE_(\w+)$/);
                if (bcField) {
                    var bcVal = vars.hasOwnProperty(bcField[1]) ? vars[bcField[1]] : '';
                    if (bcVal) {
                        cmds += buildBarcode(bcVal);
                        lineHasContent = true;
                    }
                    continue;
                }

                // --- Items block (receipt only) ---
                if (code === 'ITEMS' && vars._items) {
                    cmds += buildItemsBlock(vars._items, vars._currency || '');
                    lineHasContent = true;
                    continue;
                }

                // --- Taxes block (receipt only) ---
                if (code === 'TAXES' && vars._tax_lines) {
                    cmds += buildTaxesBlock(vars._tax_lines, vars._currency || '');
                    lineHasContent = true;
                    continue;
                }

                // --- Data code — replace with value ---
                var val = vars.hasOwnProperty(code) ? vars[code] : '';
                if (val) {
                    cmds += xmlEl('text', {}, val);
                    lineHasContent = true;
                }
            } else {
                // Plain text
                if (part.trim()) {
                    cmds += xmlEl('text', {}, part);
                    lineHasContent = true;
                }
            }
        }

        if (lineHasContent) {
            cmds += xmlEl('feed', {line: '1'});
        }
    }

    return cmds;
}

/**
 * Build ePOS XML for a QR code.
 * Uses the Epson <symbol> element with type=QRCODE_MODEL_2.
 */
function buildQrCode(content) {
    if (!content) return '';
    return '<symbol type="qrcode_model_2" level="default" width="6" align="center">'
         + escXml(content)
         + '</symbol>';
}

/**
 * Build ePOS XML for a Code128 barcode.
 * Uses the Epson <barcode> element.
 */
function buildBarcode(content) {
    if (!content) return '';
    return '<barcode type="code128" width="2" height="80" hri="below" align="center">'
         + escXml(content)
         + '</barcode>';
}

/**
 * Build ePOS XML for the logo image.
 * Uses pre-converted monochrome raster from the server (PRINTER_CONFIG).
 * Falls back to empty string if no logo is configured.
 */
function buildLogo() {
    if (!PRINTER_CONFIG.logo_raster || !PRINTER_CONFIG.logo_width) {
        return '';
    }
    return '<image width="' + PRINTER_CONFIG.logo_width
         + '" height="' + PRINTER_CONFIG.logo_height
         + '" align="center">'
         + PRINTER_CONFIG.logo_raster
         + '</image>';
}

/**
 * Build ePOS XML for the {{ITEMS}} block — lists all basket items
 * with name, quantity, unit price, and subtotal from the actual
 * confirmed order lines.
 */
function buildItemsBlock(items, currency) {
    var cmds = '';
    cmds += xmlEl('text', {}, '--------------------------------');
    cmds += xmlEl('feed', {line: '1'});
    (items || []).forEach(function(t) {
        var name = t.product_name || t.print_title || '';
        var qty = t.quantity || 1;
        var unitPrice = t.price_unit || 0;
        var subtotal = t.price_subtotal != null ? t.price_subtotal : unitPrice * qty;
        var total = t.price_total != null ? t.price_total : subtotal;
        cmds += xmlEl('text', {}, name);
        cmds += xmlEl('feed', {line: '1'});
        cmds += xmlEl('text', {}, '  ' + qty + ' x ' + unitPrice.toFixed(2) + '  = ' + subtotal.toFixed(2) + ' ' + currency);
        cmds += xmlEl('feed', {line: '1'});
        if (t.price_tax && t.price_tax > 0) {
            cmds += xmlEl('text', {}, '  incl. tax: ' + total.toFixed(2) + ' ' + currency);
            cmds += xmlEl('feed', {line: '1'});
        }
    });
    cmds += xmlEl('text', {}, '--------------------------------');
    cmds += xmlEl('feed', {line: '1'});
    return cmds;
}

/**
 * Build ePOS XML for the {{TAXES}} block — per-tax breakdown
 * like on a POS receipt.
 */
function buildTaxesBlock(taxLines, currency) {
    if (!taxLines || taxLines.length === 0) return '';
    var cmds = '';
    taxLines.forEach(function(t) {
        cmds += xmlEl('text', {}, 'of which ' + t.name + ' ' + t.amount.toFixed(2) + ' ' + currency);
        cmds += xmlEl('feed', {line: '1'});
    });
    return cmds;
}

/** Build a single XML element string. */
function xmlEl(tag, attrs, text) {
    var s = '<' + tag;
    for (var k in attrs) {
        if (attrs.hasOwnProperty(k)) {
            s += ' ' + k + '="' + escXml(String(attrs[k])) + '"';
        }
    }
    if (text != null) {
        s += '>' + escXml(String(text)) + '</' + tag + '>';
    } else {
        s += '/>';
    }
    return s;
}

/** Escape XML special characters. */
function escXml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// =====================================================================
// IoT Box / proxy printing
// =====================================================================

async function printProxy(payload) {
    var url = 'http://' + PRINTER_CONFIG.proxy_ip + ':8069/hw_proxy/print_receipt';
    var html = buildPrintHtml(payload);
    var resp = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({params: {receipt: html}}),
        signal: AbortSignal.timeout(15000),
    });
    return resp.ok;
}

// =====================================================================
// Browser print fallback
// =====================================================================

function printBrowser(payload) {
    var html = buildPrintHtml(payload);
    var w = window.open('', '_blank');
    w.document.write(html);
    w.document.close();
    w.print();
}

function buildPrintHtml(payload) {
    var h = '<html><body style="font-family:monospace;font-size:12px;">';
    h += '<h2 style="text-align:center;">TICKETS</h2>';
    h += '<p style="text-align:center;">' + escHtml(payload.dossier_name)
       + '<br/>' + escHtml(payload.customer || '') + '</p><hr/>';
    (payload.tickets || []).forEach(function(t) {
        h += '<div style="margin-bottom:12px;">';
        h += '<strong>#' + t.sequence + ' ' + escHtml(t.print_title) + '</strong><br/>';
        h += escHtml(t.print_subtitle);
        if (t.quantity > 1) h += ' x ' + t.quantity;
        h += '<br/>' + escHtml(t.order_name);
        if (t.timeslot_start) h += '<br/>' + t.timeslot_start.replace('T', ' ').substring(0, 16);
        if (t.event_name) h += '<br/>Event: ' + escHtml(t.event_name);
        if (t.registration_barcode) h += '<br/>Code: ' + t.registration_barcode;
        h += '</div><hr/>';
    });
    h += '<p style="text-align:center;">Total: ' + payload.amount_total + ' ' + escHtml(payload.currency) + '</p>';
    h += '</body></html>';
    return h;
}

/** Escape HTML special characters. */
function escHtml(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// =====================================================================
// Navigation
// =====================================================================

function goBack() {
    document.getElementById('results-section').classList.add('kiosk-hidden');
    document.getElementById('lookup-section').classList.remove('kiosk-hidden');
    document.getElementById('lookup-message').textContent = '';
    document.getElementById('print-message').textContent = '';
    document.getElementById('btn-print').disabled = false;
    document.getElementById('btn-print').textContent = TRANSLATIONS.print_tickets || 'Print Tickets';
    currentPayload = null;
}

// Enter key support (safe: only runs on the lookup page)
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        var lookupSection = document.getElementById('lookup-section');
        if (lookupSection && !lookupSection.classList.contains('kiosk-hidden')) {
            doLookup();
        }
    }
});
