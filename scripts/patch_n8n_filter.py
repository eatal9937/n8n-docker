import sqlite3
import json

db_path = "/home/captain/n8n-docker/n8n_data/database.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT nodes FROM workflow_entity WHERE id='avayaSupportSync01'")
row = cursor.fetchone()
if not row:
    print("Workflow not found!")
    exit(1)

nodes = json.loads(row[0])

new_filter_code = """
// Filter only authentic Avaya TAC related emails & prevent self-loops
const item = $input.item.json;
const from = (item.from?.text || item.from?.value?.[0]?.address || item.from || "").toString().toLowerCase();
const to = (item.to?.text || item.to?.value?.[0]?.address || item.to || "").toString().toLowerCase();
const subject = (item.subject || "").toString().toLowerCase();
const text = (item.text || item.textPlain || item.body || "").toString().toLowerCase();

// Hard block internal notifications, Jira, Atlassian, bouncebacks, or self-replies
if (from.includes("postmaster") ||
    from.includes("mailer-daemon") ||
    from.includes("atlassian.net") ||
    from.includes("jira") ||
    from.includes("jadssupport") ||
    from.includes("notifications@jadscomm.com") ||
    subject.includes("[helpdesk]") || 
    subject.includes("[jira]") ||
    subject.includes("คุณได้รับมอบหมาย") ||
    subject.includes("ใบงาน:")) {
    return [];
}

// Check if email has an official Avaya SR number or is directly from/to avaya.com
const hasAvayaSR = /\\b1-\\d{10,12}\\b/.test(subject) || /\\b1-\\d{10,12}\\b/.test(text);
const isFromAvayaDirect = from.includes("avaya.com") || to.includes("avaya.com");

if (!hasAvayaSR && !isFromAvayaDirect) {
    // Without an Avaya SR number or direct Avaya email, do NOT treat as an Avaya support ticket
    return [];
}

const isAvaya = isFromAvayaDirect ||
                hasAvayaSR ||
                subject.includes("support.avaya.com") ||
                subject.includes("business impact sr") ||
                subject.includes("service request alert");

if (isAvaya) {
    return $input.item;
}
return [];
"""

updated = False
for node in nodes:
    if node.get("name") == "Filter: Is Avaya Email?":
        print("Found Filter: Is Avaya Email? node, updating jsCode...")
        node["parameters"]["jsCode"] = new_filter_code
        updated = True
        break

if updated:
    cursor.execute("UPDATE workflow_entity SET nodes=? WHERE id='avayaSupportSync01'", (json.dumps(nodes),))
    conn.commit()
    print("Successfully updated filter node in avayaSupportSync01!")
else:
    print("Filter node not found!")

conn.close()
