import sqlite3
import json

db_path = "/home/captain/n8n-docker/n8n_data/database.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT nodes, connections FROM workflow_entity WHERE id='SZzIphpNILR0ap6N'")
row = cursor.fetchone()
if not row:
    print("Workflow not found!")
    exit(1)

nodes = json.loads(row[0])
connections = json.loads(row[1])

# 1. Update Parse & Route Events
parse_code = """
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

        const soldToMatch = text.match(/^(?:sold\\s*to|soldto|เลขไซต์|รหัสลูกค้า|ไซต์|ค้นหา\\s*sold)\\s*(.*)$/i);
        
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
        } else if (soldToMatch && soldToMatch[1]?.trim()) {
            action = 'lookup_sold_to';
            query = soldToMatch[1].trim();
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
"""

for n in nodes:
    if n.get("name") == "Parse & Route Events":
        n["parameters"]["jsCode"] = parse_code
        print("Updated Parse & Route Events")

# 2. Update Route Action
route_node = next((n for n in nodes if n.get("name") == "Route Action"), None)
if route_node:
    rules = route_node["parameters"]["rules"]["values"]
    if not any(r.get("outputKey") == "Help Guide" for r in rules):
        rules.append({
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2
                },
                "conditions": [
                    {
                        "leftValue": "={{ $json.action }}",
                        "rightValue": "help",
                        "operator": {
                            "type": "string",
                            "operation": "equals"
                        }
                    }
                ],
                "combinator": "and"
            },
            "renameOutput": True,
            "outputKey": "Help Guide"
        })
        print("Added Help Guide rule to Route Action")

# 3. Add Format Help Response node
format_help_code = """
const meta = $('Parse & Route Events').item.json;
const userId = meta.userId;

const tagPrefix = "@คุณ ";
const helpText = `${tagPrefix}📖 [คู่มือ & รวมคำสั่งลัด Captain Copilot]
━━━━━━━━━━━━━━━━━━━━
สวัสดีครับ! คุณสามารถพิมพ์สั่งงานผมในกลุ่มได้ทันที:

1️⃣ 🔍 เช็ค Sold To / รหัสไซต์ลูกค้า
• พิมพ์: Sold To [ชื่อลูกค้า/เลข]
  ตัวอย่าง: Sold To ธนชาต, เลขไซต์ ไทยประกัน, Sold To 0052085219

2️⃣ 📊 เช็คสถานะเคส / สรุปตั๋ว Odoo
• เช็คเคสตามชื่อ: เช็คเคส ธนชาต, สถานะ ไทยประกัน
• เช็คเคสทั้งหมด: มีกี่เคส, มีเคสอะไรบ้าง
• เช็คด้วยเลข SR / ตั๋ว: 1-23818343098 หรือ TKT-00057

3️⃣ 🚨 เปิดเคส / วิเคราะห์อาการส่ง Avaya TAC
• พิมพ์: เปิดเคส [ลูกค้า] [ตู้/ระบบ] [อาการเสีย/Error]
  ตัวอย่าง: เปิดเคส ลูกค้าไทยประกัน CM 8.1 โทรออกสายนอกไม่ได้ SIP 403 Forbidden
  (บอทจะวิเคราะห์อาการ + ร่างหัวข้อ + Impact + ขั้นตอนตรวจสอบให้ทันที)

4️⃣ 🌐 ลิงก์ดูตั๋ว & อัปเดต Site Engineer (ไม่ต้องล็อกอิน)
• เปิดดูตั๋วและเลือกเปลี่ยน Site Engineer ผ่าน Dropdown ได้ทันที:
  https://phongthep.lol/helpdesk/ticket/<เลขตั๋ว>

5️⃣ 💡 ถามปัญหาเทคนิค Avaya & VoIP
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
"""

help_node = next((n for n in nodes if n.get("name") == "Format Help Response"), None)
if not help_node:
    help_node = {
        "id": "format-help-response-01",
        "name": "Format Help Response",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 500],
        "parameters": {
            "jsCode": format_help_code
        }
    }
    nodes.append(help_node)
    print("Added Format Help Response node")
else:
    help_node["parameters"]["jsCode"] = format_help_code
    print("Updated Format Help Response node")

# 4. Update Send LINE Reply node to support mention
send_node = next((n for n in nodes if n.get("name") == "Send LINE Reply"), None)
if send_node:
    send_node["parameters"]["jsonBody"] = """={{
  JSON.stringify({
    replyToken: $json.replyToken,
    messages: [
      {
        type: "text",
        text: $json.text,
        ...($json.mention ? { mention: $json.mention } : {})
      }
    ]
  })
}}"""
    print("Updated Send LINE Reply to support mention")

# 5. Update connections
route_conns = connections.get("Route Action", {}).get("main", [])
while len(route_conns) < 5:
    route_conns.append([])

route_conns[4] = [
    {
        "node": "Format Help Response",
        "type": "main",
        "index": 0
    }
]
connections["Route Action"]["main"] = route_conns

connections["Format Help Response"] = {
    "main": [
        [
            {
                "node": "Send LINE Reply",
                "type": "main",
                "index": 0
            }
        ]
    ]
}
print("Updated connections for Format Help Response")

cursor.execute("UPDATE workflow_entity SET nodes=?, connections=? WHERE id='SZzIphpNILR0ap6N'", (json.dumps(nodes), json.dumps(connections)))
conn.commit()
conn.close()
print("Saved updated workflow to SQLite successfully!")
