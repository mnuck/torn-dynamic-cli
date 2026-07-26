// ==UserScript==
// @name         Torn Race Final Standings
// @namespace    https://github.com/mnuck/torn-dynamic-cli
// @version      2.3
// @description  Adds a button into the race header that reveals the final standings instantly, rendered inline below the player. Works on race-log pages and the live racing view (raceID read from the driver list when absent from the URL), and survives in-app race switching via a MutationObserver. The full result is delivered up front in the racingData payload; clicking the button decodes it. The request is only ever made on a manual click, never automatically.
// @author       WillieMcCoy
// @match        https://www.torn.com/page.php?sid=racing*
// @match        https://www.torn.com/loader.php?sid=racing*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // The anti-CSRF token the racingData endpoint requires lives in the rfc_v cookie.
    function getToken() {
        var m = document.cookie.match(/(?:^|;\s*)rfc_v=([^;]+)/);
        return m ? m[1] : null;
    }

    function getRaceID() {
        // Race log pages carry the id in the URL.
        var m = location.href.match(/[?&]raceID=(\d+)/);
        if (m) return m[1];
        // The live racing view (sid=racing, no raceID) instead lists drivers as
        // <li data-id="<raceID>-<userID>">, so pull the id from there.
        var els = document.querySelectorAll('[data-id]');
        for (var i = 0; i < els.length; i++) {
            var dm = (els[i].getAttribute('data-id') || '').match(/^(\d{6,})-\d+$/);
            if (dm) return dm[1];
        }
        return null;
    }

    function fmtTime(sec) {
        var m = Math.floor(sec / 60);
        var s = (sec - m * 60).toFixed(2);
        if (s < 10) s = '0' + s;
        return m + ':' + s;
    }

    // Each driver's car data is a base64 string -> CSV of per-segment times (92 segments x laps).
    // Summing them gives that driver's exact finish time.
    function finishTime(carValue) {
        var b64 = (typeof carValue === 'string')
            ? carValue
            : Object.keys(carValue).map(function (k) { return carValue[k]; }).join('');
        var csv = atob(b64);
        var total = 0;
        var parts = csv.split(',');
        for (var i = 0; i < parts.length; i++) total += parseFloat(parts[i]);
        return total;
    }

    // The race player's header bar is the .title-black whose text names the race
    // (e.g. "Mudpit - 15 laps - Race started"). It's present in every race state —
    // finished log, paused, or live — whereas .race-player-container is not.
    function getHeader() {
        var hs = document.querySelectorAll('.title-black');
        for (var i = 0; i < hs.length; i++) {
            var t = hs[i].textContent || '';
            if (/\blaps\b/i.test(t) && /race/i.test(t)) return hs[i];
        }
        return null;
    }

    function getPanel() {
        var h = getHeader();
        if (!h) return null;
        return h.closest('.drivers-list') || h.parentElement;
    }

    function box() {
        var b = document.getElementById('race-final-standings');
        if (!b) {
            b = document.createElement('div');
            b.id = 'race-final-standings';
            b.style.cssText = 'margin:8px 0;background:#1c1c1c;border:1px solid #444;' +
                'border-radius:6px;padding:12px 14px';
            var panel = getPanel();
            if (panel && panel.parentNode) panel.parentNode.insertBefore(b, panel.nextSibling);
            else document.body.appendChild(b);
        }
        return b;
    }

    function message(text) {
        box().innerHTML = '<div style="font:13px/1.5 Arial;color:#ddd">' + text + '</div>';
    }

    function render(data) {
        var cars = data.raceData && data.raceData.cars;
        var info = data.raceData && data.raceData.carInfo;
        if (!cars) { message('No race data available yet.'); return; }

        var rows = Object.keys(cars).map(function (name) {
            return { name: name, time: finishTime(cars[name]), userID: info && info[name] ? info[name].userID : null };
        }).sort(function (a, b) { return a.time - b.time; });

        var lead = rows[0].time;
        var html = '<div style="font:13px/1.5 Arial;color:#ddd">' +
            '<div style="font-weight:bold;color:#fff;margin-bottom:6px">Final Standings &mdash; ' +
            (data.logData ? data.logData.trackTitle : '') + ' (' + data.laps + ' laps)</div>' +
            '<table style="border-collapse:collapse;width:100%">';
        rows.forEach(function (r, i) {
            var gap = i === 0 ? '&mdash;' : '+' + (r.time - lead).toFixed(2);
            var medal = ['🥇', '🥈', '🥉'][i] || (i + 1);
            // Explicit color on every cell: Torn's stylesheet sets a dark td color that
            // would otherwise win over the panel's inherited light text.
            html += '<tr style="border-top:1px solid #333">' +
                '<td style="padding:3px 8px 3px 0;color:#ddd">' + medal + '</td>' +
                '<td style="padding:3px 8px 3px 0;color:#ddd">' +
                (r.userID
                    ? '<a style="color:#3ca0e7" href="/profiles.php?XID=' + r.userID + '">' + r.name + '</a>'
                    : r.name) +
                '</td>' +
                '<td style="padding:3px 8px 3px 0;color:#ddd;font-variant-numeric:tabular-nums">' + fmtTime(r.time) + '</td>' +
                '<td style="padding:3px 0;color:#999;font-variant-numeric:tabular-nums">' + gap + '</td>' +
                '</tr>';
        });
        html += '</table></div>';
        box().innerHTML = html;
    }

    // Fires ONLY from a manual button click — never automatically — to comply with
    // Torn's rule against non-API requests that aren't user-initiated.
    function onClick() {
        var id = getRaceID();
        var token = getToken();
        if (!id) { message('Open a specific race first (no raceID in the URL).'); return; }
        if (!token) { message('Could not read the rfc_v token.'); return; }

        message('Loading…');
        box().setAttribute('data-race', id);   // tag results so a later race-switch can clear them
        fetch('/page.php?rfcv=' + token + '&sid=racingData&raceID=' + id,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (j) {
                if (j && j.success !== false && j.raceData) render(j);
                else message('Race data unavailable.');
            })
            .catch(function () { message('Request failed.'); });
    }

    // Returns true once the button is in place; false if the race header isn't on the page yet.
    function addButton() {
        if (document.getElementById('race-final-standings-btn')) return true;
        var header = getHeader();
        if (!header) return false;
        var btn = document.createElement('button');
        btn.id = 'race-final-standings-btn';
        btn.textContent = 'Final Standings';
        btn.style.cssText = 'float:right;margin:-2px 4px 0 6px;cursor:pointer;' +
            'font:bold 11px Arial;color:#fff;background:#3a6ea5;border:1px solid #294f78;' +
            'border-radius:4px;padding:1px 8px';
        btn.addEventListener('click', onClick);
        header.appendChild(btn);
        return true;
    }

    // The racing section is a single-page app: opening a different race swaps the DOM
    // without re-running this script. A MutationObserver keeps the button attached and
    // clears stale standings when the race changes. This is DOM-only — never a network
    // request; the racingData fetch still happens solely on a manual button click.
    var lastRaceID = null;
    function sync() {
        var id = getRaceID();
        var panel = document.getElementById('race-final-standings');
        // Different race now showing? Drop the old race's standings.
        if (panel && panel.getAttribute('data-race') && panel.getAttribute('data-race') !== id) {
            panel.remove();
        }
        addButton();
        lastRaceID = id;
    }

    var observer = new MutationObserver(function () {
        // Cheap guard: do real work only when the button is gone or the race changed.
        if (!document.getElementById('race-final-standings-btn') || getRaceID() !== lastRaceID) sync();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    sync();
})();
