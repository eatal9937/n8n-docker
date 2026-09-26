#!/usr/bin/env python3
import sqlite3
import json
import sys

db_path = '/home/captain/n8n-docker/n8n_data/database.sqlite'
workflow_id = 'SZzIphpNILR0ap6N'

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get published version id
c.execute("SELECT publishedVersionId FROM workflow_published_version WHERE workflowId = ?", (workflow_id,))
pub_row = c.fetchone()
pub_ver_id = pub_row[0] if pub_row else None
print(f"Target Workflow: {workflow_id}, Published Version: {pub_ver_id}")

c.execute("SELECT nodes FROM workflow_entity WHERE id = ?", (workflow_id,))
entity_row = c.fetchone()
if not entity_row:
    print("Workflow entity not found!")
    sys.exit(1)

nodes = json.loads(entity_row[0])

# 1. Update Parse & Route Events
parse_code = '''
const body = $input.item.json.body || {};
const events = body.events || [];

const output = [];

for (const event of events) {
    if (event.type === 'message' && event.message?.type === 'text') {
        let text = event.message.text.trim();
        // Clean out bot name mentions
        text = text.replace(/@?Captain\\s*Copilot/gi, '')
                   .replace(/@?Captain/gi, '')
                   .replace(/@?Copilot/gi, '')
                   .replace(/@\\S+/g, '')
                   .replace(/บอท/g, '')
                   .trim();

        const lower = text.toLowerCase();
        const replyToken = event.replyToken;
        const source = event.source || {};
        const isGroup = source.type === 'group' || source.type === 'room';
        const groupId = source.groupId || source.roomId || null;
        const userId = source.userId || null;

        let action = 'ignore';
        let query = text;

        // Help command keywords
        const isHelpCommand = (
            text === 'ช่วยเหลือ' ||
            text === 'วิธีใช้' ||
            text === 'คำสั่ง' ||
            text === 'คู่มือ' ||
            text === 'เมนู' ||
            lower === 'help' ||
            lower === 'menu' ||
            lower === 'commands' ||
            text.includes('ช่วยเหลือ') ||
            text.includes('วิธีใช้บอท') ||
            text.includes('วิธีใช้งาน') ||
            text.includes('คำสั่งบอท')
        );

        // Daily Standup / Morning Briefing keywords
        const isStandup = (
            text === 'สรุปเช้า' ||
            text === 'standup' ||
            lower === 'standup' ||
            text === 'สรุปงานเช้า' ||
            text === 'บรีฟเช้า' ||
            text === 'รายงานเช้า' ||
            text.includes('สรุปเช้า') ||
            text.includes('สรุปงานเช้า') ||
            text.includes('บรีฟงาน')
        );

        // Customer Site / Sold To lookup keywords
        const soldToMatch = (
            text.match(/^(?:sold\\s*to|soldto|เลขไซต์|รหัสลูกค้า|ข้อมูลไซต์|ขอข้อมูลไซต์|ไซต์|ค้นหา\\s*sold|info\\s*site|info)\\s*(.*)$/i) ||
            text.match(/(.*?)\\s*(?:ข้อมูลไซต์|ขอข้อมูลไซต์)$/i)
        );
        
        // Case status / count / search detection
        const statusMatch = (
            text.match(/^(?:สถานะ|status|เช็คเคส|ตามเคส|เคส|มีกี่เคส|เช็คสถานะ)\\s*(.*)$/i) ||
            text.match(/(.*?)(?:มีกี่เคส|มีเคสอะไรบ้าง|มีเคสกี่เคส|เคสมีอะไรบ้าง|กี่เคส)/i) ||
            text.match(/\\b(1-\\d{10,12})\\b/) ||
            text.match(/\\b(TKT-\\d{5})\\b/i) ||
            (text.includes('เคส') && (text.includes('ธนชาต') || text.includes('ไทยประกัน') || text.includes('กฟน') || text.includes('ทอ') || text.includes('cimb') || text.includes('mea')))
        );
        
        // Technical problem / Incident detection keywords
        const isProblemKeywords = (
            text.includes('เปิดเคส') || lower.includes('open case') || text.includes('สร้างเคส') || text.includes('แจ้งเคส') || text.includes('เคสใหม่') ||
            text.includes('โทรไม่ได้') || text.includes('โทรออกไม่ได้') || text.includes('รับสายไม่ได้') || text.includes('สายตัด') ||
            lower.includes('reorder') || lower.includes('forbidden') || lower.includes('403') || lower.includes('503') || lower.includes('500') ||
            lower.includes('cm 8') || lower.includes('cm 7') || lower.includes('cm 6') || lower.includes('list trace') || lower.includes('sip trunk') ||
            text.includes('ลูกค้า') && (text.includes('ตู้') || text.includes('cm') || text.includes('โทร') || text.includes('อาการ') || text.includes('ปัญหา'))
        );

        const isGeneralAIChat = (
            !isGroup || event.message.text.includes('@Captain') || event.message.text.includes('@บอท') || lower.includes('avaya') || lower.includes('copilot')
        );

        if (isHelpCommand) {
            action = 'help';
            query = text;
        } else if (isStandup) {
            action = 'check_status';
            query = '__STANDUP__';
        } else if (soldToMatch && (soldToMatch[1] || soldToMatch[0])) {
            action = 'lookup_sold_to';
            query = (soldToMatch[1] || soldToMatch[0]).trim();
        } else if (statusMatch) {
            action = 'check_status';
            if (statusMatch[1] && statusMatch[1].trim()) {
                query = statusMatch[1].trim().replace(/(?:มีกี่เคส|มีเคสอะไรบ้าง|มีเคสกี่เคส|กี่เคส)/g, '').trim();
            } else if (statusMatch[0]) {
                query = statusMatch[0].trim().replace(/(?:มีกี่เคส|มีเคสอะไรบ้าง|มีเคสกี่เคส|กี่เคส)/g, '').trim();
            }
            if (!query) query = text.replace(/(?:มีกี่เคส|มีเคสอะไรบ้าง|กี่เคส|เคส)/g, '').trim();
        } else if (isProblemKeywords) {
            action = 'open_case';
            query = text.replace(/^(?:เปิดเคส|open case|สร้างเคส|แจ้งเคส|เคสใหม่)[:\\s]*/i, '').trim() || text;
        } else if (isGeneralAIChat) {
            action = 'ai_chat';
            query = text;
        }

        output.push({
            json: {
                action: action,
                query: query,
                rawText: text,
                replyToken: replyToken,
                groupId: groupId,
                userId: userId,
                isGroup: isGroup
            }
        });
    }
}

return output;
'''

# 2. Update Format Status Message
format_status_code = '''
const meta = $('Parse & Route Events').item.json;
const res = $input.item.json;
const tickets = res.data || res.tickets || [];

const stateMap = {
    'new': '🔵 ใหม่ (New)',
    'in_progress': '🟡 กำลังทำ (In Progress)',
    'pending': '⏳ รอข้อมูล (Pending)',
    'solved': '🟢 แก้ไขแล้ว (Solved)',
    'closed': '⚪ ปิดเคสแล้ว (Closed)'
};

let replyText = "";

if (meta.query === '__STANDUP__') {
    const inProgress = tickets.filter(x => x.state === 'in_progress').length;
    const closed = tickets.filter(x => x.state === 'closed' || x.state === 'solved').length;
    const newCount = tickets.filter(x => x.state === 'new').length;

    const days = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'];
    const months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
    const now = new Date(Date.now() + 7 * 3600 * 1000);
    const dayName = days[now.getUTCDay()];
    const dateStr = `วัน${dayName}ที่ ${now.getUTCDate()} ${months[now.getUTCMonth()]} ${now.getUTCFullYear() + 543}`;

    replyText = `☀️ [อรุณสวัสดิ์ทีมงาน! สรุปภารกิจประจำวัน]\\n` +
                `📅 ${dateStr}\\n` +
                `━━━━━━━━━━━━━━━━━━━━\\n` +
                `📊 สถานะภาพรวม: 🟡 กำลังทำ: ${inProgress} | 🔵 ใหม่: ${newCount} | 🟢 ปิดแล้ว: ${closed}\\n` +
                `━━━━━━━━━━━━━━━━━━━━\\n` +
                `📋 เคสที่ต้องดูแลแยกตามวิศวกร:\\n\\n`;

    const activeTickets = tickets.filter(x => x.state !== 'closed' && x.state !== 'solved' && x.state !== 'cancel');
    const grouped = {};
    for (const t of activeTickets) {
        const eng = t.site_engineer || 'Phongthep Phimthong';
        if (!grouped[eng]) grouped[eng] = [];
        grouped[eng].push(t);
    }

    if (Object.keys(grouped).length === 0) {
        replyText += `🎉 ยอดเยี่ยมมาก! ขณะนี้ไม่มีเคสค้างในระบบครับ\\n`;
    } else {
        for (const [eng, caseList] of Object.entries(grouped)) {
            replyText += `👤 @${eng} (${caseList.length} เคส):\\n`;
            for (let i = 0; i < Math.min(caseList.length, 3); i++) {
                const c = caseList[i];
                const stateEmoji = c.state === 'in_progress' ? '🟡' : (c.state === 'new' ? '🔵' : '⏳');
                replyText += `  • 🎫 ${c.ref} - ${c.customer || 'Not specified'}\\n` +
                             `    ${stateEmoji} ${c.state} | Avaya: ${c.sr_number || '-'}\\n` +
                             `    🌐 ${c.portal_url}\\n`;
            }
            if (caseList.length > 3) {
                replyText += `    ...และอีก ${caseList.length - 3} เคส\\n`;
            }
            replyText += `\\n`;
        }
    }

    replyText += `━━━━━━━━━━━━━━━━━━━━\\n` +
                 `💡 ขอให้ทุกท่านปฏิบัติงานด้วยความปลอดภัยครับ!\\n` +
                 `(พิมพ์ 'สรุปเช้า' เพื่อเรียกดูข้อมูลอัปเดตได้ตลอดเวลา)`;

    return {
        json: {
            replyToken: meta.replyToken,
            text: replyText.trim()
        }
    };
}

if (tickets.length === 1) {
    const t = tickets[0];
    const stateTh = stateMap[t.state] || t.state;
    replyText = `📌 [รายงานสถานะเคส Odoo]\\n` +
                `━━━━━━━━━━━━━━━━━━━━\\n` +
                `🎫 เลขเคส: ${t.ref || '-'}\\n` +
                `🏢 ลูกค้า: ${t.customer || '-'}\\n` +
                `👤 ผู้ดูแลไซต์: @${t.site_engineer || 'Phongthep Phimthong'}\\n` +
                `🔢 Avaya SR#: ${t.sr_number || '-'}\\n` +
                `📊 สถานะ: ${stateTh}\\n` +
                `📋 หัวข้อ: ${t.subject || '-'}\\n\\n` +
                `🌐 ดูรายละเอียดเคส (ไม่ต้องล็อกอิน):\\n${t.portal_url || ('https://phongthep.lol/helpdesk/ticket/' + t.id)}`;
} else if (tickets.length > 1) {
    const inProgress = tickets.filter(x => x.state === 'in_progress').length;
    const closed = tickets.filter(x => x.state === 'closed' || x.state === 'solved').length;
    const newCount = tickets.filter(x => x.state === 'new').length;

    replyText = `📌 [รายงานสรุปเคสในระบบ Odoo]\\n` +
                `🔍 คำค้นหา: "${meta.query}" (พบทั้งหมด ${tickets.length} เคส)\\n` +
                `📊 สรุป: 🟡 กำลังทำ: ${inProgress} | 🟢 ปิดแล้ว: ${closed}${newCount ? (' | 🔵 ใหม่: ' + newCount) : ''}\\n` +
                `━━━━━━━━━━━━━━━━━━━━\\n`;

    for (let i = 0; i < Math.min(tickets.length, 5); i++) {
        const t = tickets[i];
        const stateTh = stateMap[t.state] || t.state;
        replyText += `${i+1}. 🎫 ${t.ref} | 📊 ${stateTh}\\n` +
                     `   👤 ผู้ดูแล: @${t.site_engineer || 'Phongthep Phimthong'}\\n` +
                     `   🔢 Avaya SR: ${t.sr_number || '-'}\\n` +
                     `   📋 ${t.subject.substring(0, 70)}...\\n` +
                     `   🌐 ดูตั๋ว: ${t.portal_url}\\n` +
                     `────────────────────\\n`;
    }
} else {
    replyText = `🔍 ไม่พบข้อมูลเคสสำหรับ: "${meta.query}" ในระบบ Odoo\\nกรุณาตรวจสอบชื่อลูกค้า (เช่น ธนชาต, ไทยประกัน, กฟน) หรือเลข Avaya SR อีกครั้งครับ`;
}

return {
    json: {
        replyToken: meta.replyToken,
        text: replyText.trim()
    }
};
'''

# 3. Update Format Sold To Response
format_sold_to_code = '''
const res = $input.item.json;
const meta = $('Parse & Route Events').item.json;

let replyText = "";
if (res.success && res.data && res.data.length > 0) {
    replyText = `🏢 [ข้อมูลไซต์ & ข้อมูลลูกค้า Sold To]\\n` +
                `คำค้นหา: "${meta.query}" (พบ ${res.data.length} ไซต์)\\n` +
                `━━━━━━━━━━━━━━━━━━━━\\n`;
    
    for (let i = 0; i < Math.min(res.data.length, 3); i++) {
        const d = res.data[i];
        replyText += `🏢 ลูกค้า: ${d.customer_name}\\n` +
                     `🔢 Sold To #: ${d.sold_to || '-'}\\n` +
                     (d.phone ? `📞 เบอร์ติดต่อ: ${d.phone}\\n` : '') +
                     (d.email ? `📧 อีเมล: ${d.email}\\n` : '') +
                     `📍 ที่อยู่: ${d.address || '-'}\\n`;

        if (d.active_tickets && d.active_tickets.length > 0) {
            replyText += `📋 เคสที่กำลังดำเนินการ (${d.active_tickets.length} เคส):\\n`;
            for (const t of d.active_tickets) {
                replyText += `  • 🎫 ${t.ref} | SR#: ${t.sr_number || '-'}\\n` +
                             `    👨‍💻 ผู้ดูแล: @${t.site_engineer || 'Phongthep Phimthong'}\\n` +
                             `    🌐 ${t.portal_url}\\n`;
            }
        } else {
            replyText += `✅ ไม่มีเคสค้างในขณะนี้\\n`;
        }
        replyText += `────────────────────\\n`;
    }
} else {
    replyText = `🔍 ไม่พบข้อมูลไซต์สำหรับ: "${meta.query}"\\nกรุณาลองระบุชื่อบริษัทลูกค้า หรือ Sold To ID ใหม่อีกครั้งครับ (เช่น ธนชาต, กฟน, ไทยประกัน, CIMB, ทอ)`;
}

return {
    json: {
        replyToken: meta.replyToken,
        text: replyText.trim()
    }
};
'''

# 4. Update Format Help Response
format_help_code = '''
const meta = $('Parse & Route Events').item.json;
const userId = meta.userId;

const tagPrefix = "@คุณ ";
const helpText = `${tagPrefix}📖 [คู่มือ & รวมคำสั่งลัด Captain Copilot]
━━━━━━━━━━━━━━━━━━━━
สวัสดีครับ! คุณสามารถพิมพ์สั่งงานผมในกลุ่มได้ทันที:

1️⃣ ☀️ สรุปภารกิจประจำวัน (Standup Briefing)
• พิมพ์: สรุปเช้า หรือ standup
  (บอทจะสรุปสถานะเคสทั้งหมด และจัดกลุ่มงานตาม Site Engineer พร้อมลิงก์)

2️⃣ 🏢 เช็คข้อมูลไซต์ / Sold To ลูกค้า
• พิมพ์: Sold To [ลูกค้า] หรือ ข้อมูลไซต์ [ลูกค้า]
  ตัวอย่าง: ข้อมูลไซต์ ธนชาต, ไซต์ กฟน, Sold To 0051736999
  (แสดงรหัส Sold To, เบอร์ติดต่อ, ที่อยู่ และเคสที่กำลังดำเนินการ)

3️⃣ 📊 เช็คสถานะเคส / สรุปตั๋ว Odoo
• เช็คเคสตามชื่อ: เช็คเคส ธนชาต, สถานะ ไทยประกัน
• เช็คเคสทั้งหมด: มีกี่เคส, มีเคสอะไรบ้าง
• เช็คด้วยเลข SR / ตั๋ว: 1-23818343098 หรือ TKT-00057
  (⚡ เมื่อทีมตามเคส ระบบจะช่วย AI ร่างอีเมล Follow-up ส่งเข้า Telegram พี่กัปตัน พร้อมปุ่มกดส่งเมลออกได้ทันทีใน 1 คลิก)

4️⃣ 🚨 เปิดเคส / วิเคราะห์อาการส่ง Avaya TAC
• พิมพ์: เปิดเคส [ลูกค้า] [ตู้/ระบบ] [อาการเสีย/Error]
  ตัวอย่าง: เปิดเคส ลูกค้าไทยประกัน CM 8.1 โทรออกสายนอกไม่ได้ SIP 403 Forbidden
  (บอทจะวิเคราะห์อาการ + ร่างหัวข้อ + Impact + ขั้นตอนตรวจสอบให้ทันที)

5️⃣ 🌐 ลิงก์ดูตั๋ว & อัปเดต Site Engineer (ไม่ต้องล็อกอิน)
• เปิดดูตั๋วและเลือกเปลี่ยน Site Engineer ผ่าน Dropdown ได้ทันที:
  https://phongthep.lol/helpdesk/ticket/<เลขตั๋ว>

6️⃣ 💡 ถามปัญหาเทคนิค Avaya & VoIP
• พิมพ์: @Captain [คำถาม] เช่น @Captain คำสั่ง trace sip ใน CM
━━━━━━━━━━━━━━━━━━━━
💡 พิมพ์ "ช่วยเหลือ" ได้ทุกเมื่อเพื่อดูคู่มือนี้อีกครั้งครับ`;

const result = {
    replyToken: meta.replyToken,
    text: helpText.trim()
};

if (userId) {
    result.mention = {
        mentionees: [
            {
                index: 0,
                length: tagPrefix.trim().length,
                userId: userId
            }
        ]
    };
}

return { json: result };
'''

# 5. Update Format Telegram Follow-up Alert (with Inline Button)
format_telegram_code = '''
const groqResp = $input.item.json;
const draft = groqResp.choices?.[0]?.message?.content || "Could not generate follow-up draft.";

const meta = $('Parse & Route Events').item.json;
const tDetail = $('Fetch Ticket Detail').item.json.ticket || {};
const msgs = $('Fetch Ticket Detail').item.json.messages || [];

let lastSnippet = "-";
if (msgs.length > 0) {
    const m = msgs[0];
    let clean = (m.body || "").replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim().substring(0, 250);
    lastSnippet = `<b>${m.author || 'Support'}:</b> ${clean}`;
}

const uid = meta.userId;
let requester = "@ทีมงาน";
if (uid === "U7065613de16484ec6166f78c33eb1bb6") {
    requester = "@Captain (Phongthep)";
}

const escapeHtml = (s) => (s || "").toString().replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const telegramHtml = `🔔 <b>[แจ้งเตือนทีมตามเคส ➔ ร่างเมล Follow-up]</b>\\n\\n` +
`👤 <b>ผู้ตามงานใน LINE:</b> ${escapeHtml(requester)}\\n` +
`💬 <b>ข้อความ:</b> "${escapeHtml(meta.rawText)}"\\n` +
`🏢 <b>ลูกค้า:</b> ${escapeHtml(tDetail.customer || '-')}\\n` +
`🎫 <b>ตั๋ว Odoo:</b> #${escapeHtml(tDetail.ref || String(tDetail.id))} (ID: ${tDetail.id})\\n` +
`🔢 <b>Avaya SR#:</b> ${escapeHtml(tDetail.avaya_sr_number || '-')}\\n` +
`📊 <b>สถานะ:</b> ${escapeHtml(tDetail.state || '-')} | ${escapeHtml(tDetail.avaya_status || '-')}\\n` +
`👨‍💻 <b>Site Engineer:</b> ${escapeHtml(tDetail.site_engineer || 'Phongthep Phimthong')}\\n\\n` +
`📩 <b>ความคืบหน้า/เมลล่าสุด:</b>\\n` +
`<i>${lastSnippet}</i>\\n\\n` +
`📝 <b>AI ร่างเมล Follow-up พร้อมส่ง Avaya:</b>\\n` +
`<pre>${escapeHtml(draft)}</pre>\\n\\n` +
`🌐 <a href="${tDetail.portal_url || ('https://phongthep.lol/helpdesk/ticket/' + tDetail.id)}">เปิดดูตั๋วใน Odoo</a>`;

return {
    json: {
        chat_id: 8948351323,
        text: telegramHtml,
        parse_mode: "HTML",
        disable_web_page_preview: true,
        reply_markup: {
            inline_keyboard: [
                [
                    {
                        text: "📤 ส่งเมล Follow-up นี้ทันที",
                        callback_data: "send_followup:" + tDetail.id
                    }
                ]
            ]
        }
    }
};
'''

# Apply updates to nodes
for n in nodes:
    name = n.get('name')
    if name == 'Parse & Route Events':
        n['parameters']['jsCode'] = parse_code.strip()
        print("- Updated Parse & Route Events")
    elif name == 'Query Odoo Ticket':
        n['parameters']['url'] = "=https://phongthep.lol/helpdesk/api/search_tickets?query={{ $json.query === '__STANDUP__' ? '' : encodeURIComponent($json.query) }}"
        print("- Updated Query Odoo Ticket URL parameter")
    elif name == 'Format Status Message':
        n['parameters']['jsCode'] = format_status_code.strip()
        print("- Updated Format Status Message")
    elif name == 'Format Sold To Response':
        n['parameters']['jsCode'] = format_sold_to_code.strip()
        print("- Updated Format Sold To Response")
    elif name == 'Format Help Response':
        n['parameters']['jsCode'] = format_help_code.strip()
        print("- Updated Format Help Response")
    elif name == 'Format Telegram Follow-up Alert':
        n['parameters']['jsCode'] = format_telegram_code.strip()
        print("- Updated Format Telegram Follow-up Alert")
    elif name == 'Send LINE Reply':
        n['onError'] = 'continueRegularOutput'
        n['continueOnFail'] = True
        print("- Updated Send LINE Reply continueOnFail")
    elif name == 'Check If Ticket Found for Alert':
        conds = n.get('parameters', {}).get('conditions', {}).get('conditions', [])
        if conds:
            conds[0]['leftValue'] = "={{ Boolean($json.data && $json.data.length > 0 && $('Parse & Route Events').item.json.query !== '__STANDUP__') }}"
            print("- Updated Check If Ticket Found for Alert condition")

updated_nodes_json = json.dumps(nodes)

c.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?", (updated_nodes_json, workflow_id))
print("Updated workflow_entity")

if pub_ver_id:
    c.execute("UPDATE workflow_history SET nodes = ? WHERE workflowId = ? AND versionId = ?", (updated_nodes_json, workflow_id, pub_ver_id))
    print(f"Updated workflow_history for version {pub_ver_id}")

conn.commit()
conn.close()
print("Workflow update completed successfully!")
