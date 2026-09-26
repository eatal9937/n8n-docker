// Unified Avaya Email Parser for n8n (Supports Modern HTML Tables & Legacy Formats)
const item = $input.item.json;
let body = (item.text || item.textPlain || item.body || item.message || "").toString();
let html = (item.html || "").toString();

// 1. If body is empty but html exists, strip tags while PRESERVING newlines
if (!body && html) {
    let cleanHtml = html.replace(/<(style|script)[^>]*>[\s\S]*?<\/\1>/gi, ' ');
    cleanHtml = cleanHtml.replace(/<br\s*[\/]?>/gi, '\n')
                         .replace(/<\/(p|div|tr|td)>/gi, '\n');
    body = cleanHtml.replace(/<[^>]+>/g, ' ')
                    .replace(/&nbsp;/gi, ' ')
                    .replace(/&amp;/gi, '&')
                    .replace(/[ \t]+/g, ' ')
                    .replace(/\n\s*\n+/g, '\n\n')
                    .trim();
}

// 2. Table Extraction (Modern Avaya Open Notification & Siebel Alerts)
const tableMap = {};
if (html) {
    const rowRegex = /<tr[^>]*>\s*<td[^>]*>([\s\S]*?)<\/td>\s*<td[^>]*>([\s\S]*?)<\/td>\s*<\/tr>/gi;
    let m;
    while ((m = rowRegex.exec(html)) !== null) {
        const k = m[1].replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ').replace(/:/g, '').trim().toLowerCase();
        const v = m[2].replace(/<[^>]+>/g, ' ').replace(/&nbsp;/gi, ' ').replace(/&#xD;/gi, '').replace(/\s+/g, ' ').trim();
        if (k) {
            tableMap[k] = v;
        }
    }
}

// 3. Known boundary tokens to avoid run-away regex matches
const fieldBoundaries = '(?:\\bSR\\s*(?:Number|#)?|\\bBusiness\\s*Severity|\\bSeverity|\\bSold\\s*To\\s*Name|\\bSold\\s*To\\s*Address|\\bSold\\s*To\\b|\\bFL\\b|\\bContact\\s*Name|\\bContact\\b|\\bPhone\\s*Number|\\bContact\\s*Phone|\\bPhone\\b|\\bContact\\s*Email|\\bEmail\\b|\\bDate\\s*Reported|\\bOpened\\b|\\bCreated\\b|\\bStatus\\b|\\bProduct\\b|\\bAsset\\s*ID|\\bElement\\s*Nick\\s*Name|\\bHost\\s*Name|\\bDescription\\b|\\bComments\\b|\\bOwner\\s*-\\s*SBL|\\*\\s*This\\s*notification|\\bAlert\\s*ID|\\bOn-Line\\s*Support|\\bManagement\\s*Escalation|\\bOpt-Out|\\r?\\n|$)';

function extractWithBoundary(keyPattern, text) {
    if (!text) return "";
    const re = new RegExp(keyPattern + '\\s*[:\\-]?\\s*([^\\r\\n]+?)(?=\\s*' + fieldBoundaries + ')', 'i');
    const m = text.match(re);
    if (m) {
        return m[1].replace(/[;,\s]+$/, '').trim();
    }
    return "";
}

const emailSubject = (item.subject || "").toString();
const fullSearchText = `${emailSubject}\n${body}`;

// SR Number
let srNumber = tableMap['sr number'] || tableMap['service request number'] || tableMap['sr#'] || tableMap['case'];
if (!srNumber || !/^[0-9\-]+$/.test(srNumber.trim())) {
    const m = fullSearchText.match(/\b(1-\d{10,12})\b/);
    if (m) {
        srNumber = m[1];
    } else {
        const m2 = fullSearchText.match(/SR\s*(?:Number|#)?[\s:]*([0-9\-]{8,15})/i);
        if (m2) srNumber = m2[1];
    }
}

// Sold To
let soldTo = tableMap['sold to'] || tableMap['fl'] || tableMap['functional location'];
if (!soldTo) {
    soldTo = extractWithBoundary('Sold\\s*To(?!\\s*(?:Name|Address))', body);
}
if (!soldTo) {
    const m = fullSearchText.match(/\b(005\d{7})\b/);
    if (m) soldTo = m[1];
}
if (!soldTo) soldTo = '0050280387';

// Customer Name
let customerName = tableMap['sold to name'] || tableMap['primary customer'];
if (!customerName) {
    customerName = extractWithBoundary('(?:Sold\\s*To\\s*Name|Primary\\s*Customer)', body);
}
if (customerName) {
    customerName = customerName.replace(/\[.*$/, '').trim();
}

// Location
let location = tableMap['sold to address'] || tableMap['location'];
if (!location) {
    location = extractWithBoundary('(?:Sold\\s*To\\s*Address|Location)', body);
}

// Contact Name
let contactName = tableMap['contact name'] || tableMap['contact'];
if (!contactName) {
    contactName = extractWithBoundary('(?:Contact\\s*Name|\\bContact\\b\\s*[:\\-])', body);
}
if (!contactName) {
    contactName = item.from?.text || (typeof item.from === 'string' ? item.from : '') || 'Phongthep Phimthong';
}
contactName = contactName.replace(/\[.*$/, '').trim();

// Contact Phone
let contactPhone = tableMap['phone number'] || tableMap['contact phone'] || tableMap['phone'];
if (contactPhone && !/\d{7,}/.test(contactPhone)) {
    contactPhone = '';
}
if (!contactPhone) {
    const m = body.match(/(?:Phone\s*Number|Contact\s*Phone|\bPhone\b)[\s:]*([0-9+\-\s()]{8,15})/i);
    if (m) contactPhone = m[1].trim();
}
if (!contactPhone) contactPhone = '0612438275';

// Contact Email
let contactEmail = tableMap['contact email'] || tableMap['email'];
if (!contactEmail || !contactEmail.includes('@')) {
    const m = body.match(/[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}/);
    if (m) contactEmail = m[0];
}
if (!contactEmail) contactEmail = 'phongthep@jadscomm.com';

// Description & Comments
let rawDesc = tableMap['description'] || extractWithBoundary('(?:Description|SR\\s*Description)', body);
let rawComments = tableMap['comments'] || extractWithBoundary('Comments', body);
let desc = rawDesc || rawComments || '';
desc = desc.replace(/^URGENT\s+P[1-4]:\s*/i, '').trim();

// Product
let product = tableMap['product'] || tableMap['op skill'];
if (!product) {
    product = extractWithBoundary('(?:Product|Op\\s*Skill)', body);
}

// Product deduction if empty or generic
if (!product || product === 'SEID' || product === 'Avaya Solution' || product === 'Collaboration Environment') {
    const combined = `${emailSubject} ${desc} ${body}`;
    if (/push notification|push/i.test(combined)) {
        product = 'Avaya Aura® Session Manager (SM) / Workplace Push Notification';
    } else if (/Communication Manager|\bCM\b/i.test(combined)) {
        product = 'Avaya Aura® Communication Manager (CM)';
    } else if (/Session Manager|\bSM\b/i.test(combined)) {
        product = 'Avaya Aura® Session Manager (SM)';
    } else if (/AADS|Device Services/i.test(combined)) {
        product = 'Avaya Aura® Device Services (AADS)';
    } else if (/Breeze|Collaboration Environment/i.test(combined)) {
        product = 'Avaya Breeze Platform';
    } else if (/SBC|ASBCE|Border Controller/i.test(combined)) {
        product = 'Avaya Session Border Controller (ASBCE)';
    } else if (/AAMS|Media Server/i.test(combined)) {
        product = 'Avaya Aura® Media Server (AAMS)';
    } else if (/IP Office|\bIPO\b/i.test(combined)) {
        product = 'Avaya IP Office (IPO)';
    } else {
        product = 'Avaya Solution';
    }
}

// Asset ID & Support Group
let assetId = tableMap['asset id'] || extractWithBoundary('Asset\\s*ID', body);
let ownerSbl = tableMap['owner - sbl'] || extractWithBoundary('Owner\\s*-\\s*SBL', body);

// Severity
let rawSev = tableMap['business severity'] || tableMap['severity'] || extractWithBoundary('(?:Business\\s*Severity|Severity)', body);
let severity = 'p3';
let priority = '1';
if (/Outage|OTG|P1|CRITICAL|URGENT/i.test(rawSev || fullSearchText)) {
    severity = 'p1';
    priority = '3';
} else if (/Major|Business Impact|P2/i.test(rawSev || fullSearchText)) {
    severity = 'p2';
    priority = '2';
} else if (/Minor|P3/i.test(rawSev || fullSearchText)) {
    severity = 'p3';
    priority = '1';
} else if (/P4|Info/i.test(rawSev || fullSearchText)) {
    severity = 'p4';
    priority = '0';
}

// Status & Date Reported
let status = tableMap['status'] || extractWithBoundary('Status', body) || 'Created';
let dateReported = tableMap['date reported'] || tableMap['opened'] || extractWithBoundary('(?:Date\\s*Reported|Opened|Created)', body);

// Summary & Subject formatting
let summary = '';
if (desc && desc !== 'Break/Fix' && desc.length > 5) {
    const firstLine = desc.split('\n')[0].trim();
    if (firstLine.length > 85) {
        const sentences = firstLine.split(/\.\s+/);
        summary = (sentences && sentences[0].length > 10) ? sentences[0].trim() : firstLine.substring(0, 85).trim();
    } else {
        summary = firstLine;
    }
} else if (emailSubject) {
    summary = emailSubject.replace(/^(?:Fwd:\s*|New Activity:\s*|BUSINESS IMPACT SR (?:Opened|Updated):\s*|Your request has been successfully created\.\.\.\s*)/i, '').trim();
}

if (!summary || summary === 'Break/Fix' || summary.length < 5) {
    summary = `${product} - Service Request`;
}

if (summary && /^[a-z]/.test(summary)) {
    summary = summary[0].toUpperCase() + summary.slice(1);
}

let custShort = '';
if (customerName) {
    const cLow = customerName.toLowerCase();
    if (cLow.includes('thanachart')) {
        custShort = 'Thanachart';
    } else if (cLow.includes('electricity') || cLow.includes('mea')) {
        custShort = 'MEA';
    } else {
        custShort = customerName.split(/\s+/)[0];
    }
}

let cleanSubject = '';
if (custShort && !summary.toLowerCase().includes(custShort.toLowerCase())) {
    cleanSubject = srNumber ? `[Avaya SR# ${srNumber}] ${summary} (${custShort})` : `${summary} (${custShort})`;
} else {
    cleanSubject = srNumber ? `[Avaya SR# ${srNumber}] ${summary}` : summary;
}

const avayaUrl = srNumber ? `https://support.avaya.com/support/en/secure/service-requests/displaySR?srNum=${srNumber}` : 'https://support.avaya.com/';
const opsReportUrl = srNumber ? `https://report.avaya.com/siebelreports/casedetails.aspx?case_id=${srNumber}` : 'https://report.avaya.com/';

function getCleanReplyText(text) {
    if (!text) return "";
    let clean = text;
    const splitRegex = /(?:\r?\n--\s*\r?\n|\r?\n_{5,}|\r?\n-{5,}|\r?\nFrom:[\s\S]*?\r?\nSent:|\r?\nOn [\s\S]*? wrote:|\r?\n>+)/i;
    const parts = clean.split(splitRegex);
    if (parts.length > 1 && parts[0].trim().length > 10) {
        clean = parts[0].trim();
    }
    return clean.trim();
}
const cleanReply = getCleanReplyText(body);

const fromLower = (item.from?.text || item.from?.value?.[0]?.address || item.from || "").toString().toLowerCase();
const toText = (item.to?.text || item.to?.value?.[0]?.address || item.to || "Avaya Support").toString();
const isOutbound = fromLower.includes("jadscomm.com") || toText.toLowerCase().includes("avaya.com");

const displayProblemDesc = (rawComments && rawComments.length > 5 && rawComments !== desc) 
    ? `${desc}\n\nAdditional Details:\n${rawComments}` 
    : (desc || summary);

const borderColor = severity === 'p1' ? '#d93025' : '#f9ab00';
const bgColor = severity === 'p1' ? '#fce8e6' : '#fef7e0';
const textColor = severity === 'p1' ? '#d93025' : '#b06000';

const htmlDescription = `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #202124;">
  <div style="background-color: ${bgColor}; border-left: 5px solid ${borderColor}; padding: 14px; margin-bottom: 16px; border-radius: 4px;">
    <div style="font-size: 16px; font-weight: bold; color: ${textColor}; margin-bottom: 8px;">
      🔔 AVAYA TAC ${severity.toUpperCase()} SERVICE REQUEST (${status})
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px;">
      <div><strong>SR Number:</strong> ${srNumber || 'N/A'}</div>
      <div><strong>Status:</strong> ${status}</div>
      <div><strong>Sold To / FL:</strong> ${soldTo}</div>
      <div><strong>Product:</strong> ${product}</div>
      <div><strong>Asset ID:</strong> ${assetId || '-'}</div>
      <div><strong>Severity:</strong> ${severity.toUpperCase()}</div>
      <div><strong>Date Reported:</strong> ${dateReported || '-'}</div>
      <div><strong>Support Group (SBL):</strong> ${ownerSbl || '-'}</div>
      ${customerName ? `<div><strong>Primary Customer:</strong> ${customerName}</div>` : ''}
      <div><strong>Location:</strong> ${location || '-'}</div>
    </div>
  </div>
  
  <div style="margin-bottom: 16px;">
    <h3 style="margin-top: 0; color: #1a73e8; font-size: 15px;">Summary / Description</h3>
    <p style="white-space: pre-wrap; background: #f8f9fa; padding: 12px; border-radius: 4px; border: 1px solid #dadce0;">${displayProblemDesc}</p>
  </div>

  <div style="margin-bottom: 16px;">
    <h3 style="margin-top: 0; color: #1a73e8; font-size: 15px;">Contact Information</h3>
    <p><strong>Contact:</strong> ${contactName} | <strong>Phone:</strong> ${contactPhone} | <strong>Email:</strong> ${contactEmail}</p>
  </div>

  <div style="margin-top: 20px; padding-top: 12px; border-top: 1px solid #dadce0;">
    <a href="${avayaUrl}" target="_blank" style="background-color: #d93025; color: white; padding: 8px 14px; text-decoration: none; border-radius: 4px; font-weight: bold; margin-right: 10px; display: inline-block;">🔗 Open Avaya TAC SR</a>
    <a href="${opsReportUrl}" target="_blank" style="background-color: #1a73e8; color: white; padding: 8px 14px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">📊 View Siebel Case Report</a>
  </div>
</div>
`;

return {
    json: {
        subject: cleanSubject,
        description: htmlDescription,
        clean_reply: cleanReply,
        raw_body: body,
        is_outbound: isOutbound,
        recipient: toText,
        ticket_type: 'incident',
        ticket_source: 'avaya_support',
        is_avaya_support: true,
        avaya_sr_number: srNumber,
        sold_to_id: soldTo,
        avaya_product: product,
        avaya_asset_id: assetId || '',
        avaya_severity: severity,
        avaya_status: status,
        priority: priority,
        avaya_contact_name: contactName,
        avaya_contact_phone: contactPhone,
        avaya_contact_email: contactEmail,
        avaya_date_reported: dateReported || '',
        avaya_customer_name: customerName || '',
        avaya_location: location || '',
        avaya_owner_sbl: ownerSbl || '',
        avaya_portal_url: avayaUrl
    }
};
