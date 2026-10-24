# ผังการทำงาน

ผังชุดเดียวกับที่ใช้ตรวจตรรกะระหว่างออกแบบ คำศัพท์เป็นไปตาม [CONTEXT.md](../CONTEXT.md) และการตัดสินใจทั้งหมดอยู่ใน [decisions.md](decisions.md)

## ผัง 1 · ภาพรวมระบบ

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#EEF3FF", "primaryTextColor": "#1B2530", "primaryBorderColor": "#2A55C6", "lineColor": "#556170", "clusterBkg": "#F6F8FA", "clusterBorder": "#C9D2DC", "titleColor": "#1B2530", "edgeLabelBackground": "#FFFFFF", "fontSize": "15px"}}}%%
flowchart LR
  subgraph STU["Student"]
    S1["หน้าทำชุดคำถาม<br/>Mastery Bar · แผงคำใบ้ · แชต"]
  end
  subgraph ENG["Backend Engine (FastAPI)"]
    M1["โมดูล 1<br/>Data Cleaning + กฎ 3 ด่าน<br/>เก็บ Flow Position"]
    M2["โมดูล 2<br/>Fuzzy Logic ทุกครั้งที่ตอบ<br/>K-Means ทั้งห้อง"]
    M3["โมดูล 3 · AI Tutor<br/>RAG + prompt 4 กรอบ<br/>+ Answer-Leak Guard"]
  end
  subgraph DATA["คลังข้อมูลในเครื่อง"]
    D1[("Digital Traces<br/>Flow Position · Decision Trace")]
    D2[("เนื้อหา<br/>Knowledge Map · Question Sets<br/>Bug Library · Authored Hints")]
    D3[("เอกสารวิชา<br/>ค้นด้วย BM25 + ตัดคำไทย")]
    D4[("Roster<br/>รหัส ↔ ชื่อจริง")]
    D0["Simulated Cohort<br/>Demo Mode"]
  end
  subgraph EXT["Provider ภายนอก"]
    P1["Claude"]
    P2["Gemini"]
  end
  subgraph TCH["Teacher"]
    T1["แดชบอร์ด<br/>สถานะภาษาคน · Risk Score<br/>Cluster · Teacher Alert"]
    T2["Manual Override"]
    T3["สร้าง Question Set<br/>อัปโหลดเอกสาร"]
  end
  subgraph ADM["Admin"]
    A1["7 แท็บตาม outline<br/>ผังสดพร้อมตำแหน่งนักเรียน"]
    A2["ตั้งค่า AI · API key<br/>ค่าพารามิเตอร์"]
    A3["Scenario · Stress Test"]
  end
  S1 -->|"Digital Trace ทุกการกระทำ"| M1
  M1 -->|"บันทึก"| D1
  M1 -->|"ตัวชี้วัด"| M2
  M2 -->|"ระดับความช่วยเหลือ"| M3
  M2 -->|"โจทย์ถัดไป · Mastery Bar"| S1
  M3 -->|"ค้นข้อผิดพลาด"| D2
  M3 -->|"ค้นเอกสาร"| D3
  M3 -->|"prompt 4 กรอบ"| P1
  M3 -->|"prompt 4 กรอบ"| P2
  M3 -->|"คำใบ้ที่ผ่าน Guard"| S1
  D0 -->|"ข้อมูลจำลอง"| D1
  D1 -->|"ส่งสด"| T1
  D1 -->|"ส่งสด · เห็นแค่รหัส"| A1
  D4 -->|"เฉพาะครู"| T1
  M2 -->|"Risk Score · Cluster"| T1
  M1 -->|"Teacher Alert"| T1
  T2 -->|"คำสั่งครูมาก่อนกฎ"| M1
  T3 -->|"เขียน"| D2
  T3 -->|"อัปโหลด"| D3
  A2 -.->|"key"| M3
  A2 -.->|"ค่าพารามิเตอร์"| M1
  A3 -->|"นักเรียนจำลองตาม Scenario"| M1
  classDef human fill:#DDF1E9,stroke:#1F7A59,stroke-width:1.5px
  classDef admin fill:#E7EBF1,stroke:#4A5A70,stroke-width:1.5px
  class T1,T2,T3 human
  class A1,A2,A3 admin
```

ทุกการกระทำของนักเรียนเข้าโมดูล 1 ก่อนเสมอ หน้าจอนักเรียนได้รับแค่โจทย์ถัดไป แถบ Mastery และคำใบ้ที่ผ่าน Answer-Leak Guard แล้ว Teacher เห็นชื่อจริงผ่าน Roster ส่วน Admin เห็นตัวแปรทุกตัวแต่เห็นนักเรียนเป็นรหัสเท่านั้น

## ผัง 2 · เมื่อนักเรียนส่งคำตอบหนึ่งครั้ง

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#EEF3FF", "primaryTextColor": "#1B2530", "primaryBorderColor": "#2A55C6", "lineColor": "#556170", "clusterBkg": "#F6F8FA", "clusterBorder": "#C9D2DC", "titleColor": "#1B2530", "edgeLabelBackground": "#FFFFFF", "fontSize": "15px"}}}%%
flowchart TD
  A(["นักเรียนส่งคำตอบ"]) --> NF{"ส่งซ้ำภายใน<br/>1 วินาที?"}
  NF -->|"ใช่"| NF1["รวมเป็นการส่งครั้งเดียว"]
  NF -->|"ไม่"| FM{"รูปแบบคำตอบ<br/>ถูกต้อง?"}
  FM -->|"ไม่"| FM1["บอกให้แก้รูปแบบ<br/>ไม่นับเป็น Attempt"]
  FM -->|"ใช่"| CL["Data Cleaning<br/>ตัดเวลาส่วนที่เกิน 5 นาที<br/>คำนวณตัวชี้วัด"]
  CL --> G1{"ด่าน 1<br/>ตอบถูก?"}

  G1 -->|"ถูก"| MU["อัปเดต Mastery ของ Concept<br/>ถ่วงน้ำหนักตามคำใบ้ที่ใช้<br/>+ Cross-Format Check"]
  MU --> HU{"ข้อนี้ผ่าน<br/>ด้วยคำใบ้?"}
  HU -->|"ใช่ · L1–L3"| ISN["ข้อถัดไปเป็น Isomorphic Test<br/>ปิดคำใบ้ทั้งหมด"]
  HU -->|"ไม่"| FIN{"ถึงเกณฑ์จบชุด?<br/>Mastery ≥ 0.8 และ<br/>Main Item ครบหรือ Challenge ถูก"}
  FIN -->|"ถึง"| END1(["จบชุด"])
  FIN -->|"ยัง แต่ครบ 20 ข้อ"| CAP(["จบ Session · บันทึกความคืบหน้า<br/>Teacher Alert เงียบ"])
  FIN -->|"ยัง"| RT{"Mastery"}
  RT -->|"≥ 0.8 และเร็วกว่าที่คาด"| FT["Fast-Track<br/>Challenge Item"]
  RT -->|"0.5 – 0.79"| SF["Standard Flow"]
  RT -->|"ต่ำกว่า 0.5"| SP["Supported Flow<br/>ง่ายลง 1 ขั้น"]
  FT --> FZ["Fuzzy Logic<br/>เลือกความยากข้อถัดไป"]
  SF --> FZ
  SP --> FZ

  G1 -->|"ผิด"| IW{"อยู่ใน<br/>Isomorphic Test?"}
  IW -->|"ใช่ · ผิดครั้งแรก"| IA1["ให้ลองอีก 1 ครั้ง<br/>ยังไม่มีคำใบ้"]
  IW -->|"ใช่ · ผิดครั้งที่ 2"| IA2["ไม่ผ่าน<br/>ข้อก่อนหน้าได้น้ำหนัก 0<br/>เปิดคำใบ้คืน"]
  IA2 --> IA3{"ไม่ผ่าน Isomorphic<br/>2 รอบติดใน Concept นี้?"}
  IA3 -->|"ไม่"| SF
  IA3 -->|"ใช่"| IMP
  IW -->|"ไม่"| G2{"ด่าน 2<br/>เร็วกว่าเวลาอ่านขั้นต่ำ?"}
  G2 -->|"ใช่"| RG["Rapid Guess<br/>คะแนนข้อนี้เป็นโมฆะ<br/>ไม่เพิ่ม Error Count<br/>ล็อกปุ่มตอบ 15 วินาที"]
  G2 -->|"ไม่"| BUG{"วินิจฉัยกับ<br/>Bug Library"}
  BUG -->|"Misconception"| FL2["Hint Floor = L2<br/>บันทึกแท็กขึ้นแดชบอร์ดครู"]
  BUG -->|"Slip · Mastery ≥ 0.5"| FL1["Hint Floor = L1"]
  BUG -->|"อื่น ๆ"| FL0["Unclassified<br/>AI เสนอแท็กได้ รอครูยืนยัน"]
  FL2 --> G3
  FL1 --> G3
  FL0 --> G3
  G3{"ด่าน 3<br/>Error Count ของข้อนี้"}
  G3 -->|"1"| H1["Deliberate Delay 15 วินาที<br/>แล้วแสดง L1<br/>หรือระดับ Floor ถ้าสูงกว่า"]
  G3 -->|"2"| H2["แสดง L2"]
  G3 -->|"3"| TT{"Fuzzy Logic<br/>เวลาคิดยาวขึ้นต่อเนื่อง?"}
  TT -->|"ไม่"| H3["L3 Bottom-out<br/>แสดงเฉพาะขั้นแรก"]
  TT -->|"ใช่"| IMP
  G3 -->|"4 ขึ้นไป · ผิดหลังเห็น L3"| IMP["Impasse<br/>พักข้อนี้ไว้ก่อน"]
  RG --> RE(["ตอบใหม่"])
  IA1 --> RE
  H1 --> RE
  H2 --> RE
  H3 --> RE

  IMP --> RC{"ข้อนี้ส่งไป Remedial<br/>ครบ 2 รอบแล้ว?"}
  RC -->|"ครบแล้ว"| DL["Stagnation Deadlock<br/>หยุดลูป · Teacher Alert"]
  RC -->|"ยัง"| PQ{"Concept นี้มี<br/>Prerequisite?"}
  PQ -->|"มี"| REM["Remedial Loop<br/>Prerequisite ที่ผูกกับ Misconception<br/>หรือที่ Mastery ต่ำสุด"]
  PQ -->|"ไม่มี"| ROOT["Walkthrough Example<br/>+ โจทย์ง่ายลงใน Concept เดิม<br/>นับเป็น 1 รอบ"]
  REM --> RR{"ผลในข้อซ่อมเสริม"}
  RR -->|"ถูก 2 ข้อติดกัน"| BK["กลับไปข้อเดิม<br/>Error Count เริ่มใหม่"]
  RR -->|"เกิด Impasse ซ้ำ"| CB["Circuit Breaker<br/>พักสายตา 1 นาที"]
  CB --> WT["Walkthrough Example<br/>ปิดรอบซ่อมเสริมนี้"]
  WT --> RC
  ROOT --> BK

  classDef human fill:#DDF1E9,stroke:#1F7A59,stroke-width:1.5px
  classDef care fill:#E9E5F7,stroke:#6A59AE,stroke-width:1.5px
  class DL human
  class CB,WT care
```

ฝั่งตอบถูกจะอัปเดต Mastery แล้วเลือก Learning Path ฝั่งตอบผิดไล่จากด่าน 2 (ตอบเร็วเกินไปหรือไม่) ไปวินิจฉัยกับ Bug Library แล้วเข้าด่าน 3 (ผิดเป็นครั้งที่เท่าไร) ทุกทางที่วนกลับมีตัวนับกำกับ วงวนจึงจบที่ครูเสมอเมื่อส่งซ่อมเสริมครบ 2 รอบ

## Flow Position

นักเรียนหนึ่งคนอยู่ได้ทีละตำแหน่ง หน้า Admin วางจุดของนักเรียนบนตำแหน่งเหล่านี้ และทุกการย้ายตำแหน่งบันทึกเหตุผลเป็น Decision Trace ส่วน Learning Path (Fast-Track, Standard, Supported) แสดงเป็นป้ายคู่กับตำแหน่ง ([ADR-0002](adr/0002-named-flow-positions.md))

| Flow Position | เข้ามาเมื่อ | ไปต่อเมื่อ |
|---|---|---|
| กำลังคิด | เปิดโจทย์ใหม่ หลังได้คำใบ้ หรือหลังปลดล็อก | ส่งคำตอบ |
| Deliberate Delay | ผิดครั้งแรก | ครบ 15 วินาทีแล้วได้คำใบ้ หรือแก้เองถูกก่อน |
| ล็อก Rapid Guess | ผิดเร็วกว่าเวลาอ่านขั้นต่ำ | ครบ 15 วินาที กลับไปกำลังคิด |
| Hint L1 · L2 · L3 | ตามบันไดคำใบ้และ Hint Floor | ส่งคำตอบ |
| Isomorphic Test | ผ่านข้อก่อนหน้าด้วยคำใบ้ | ถูก ไปเส้นทางถัดไป · ผิด 2 ครั้ง กลับ Standard Flow |
| Impasse | ผิดครั้งที่ 3 และเวลาคิดยาวขึ้น · ผิดหลังเห็น L3 · ไม่ผ่าน Isomorphic 2 รอบติด | ทันที ไป Remedial Loop หรือ Stagnation Deadlock |
| Remedial Loop รอบ 1 · 2 | Impasse และยังส่งซ่อมเสริมไม่ครบ 2 รอบ | ถูก 2 ข้อติดกัน กลับข้อเดิม · Impasse ซ้ำ ไป Circuit Breaker |
| Circuit Breaker | Impasse ใน Remedial Loop · ข้อความเครียดหรือท้อ | ครบ 1 นาที ไป Walkthrough |
| Walkthrough | หลัง Circuit Breaker · Concept ที่ไม่มี Prerequisite | อ่านจบ ไปตามเงื่อนไขในผัง 2 |
| Idle Pause | ไม่มีการกระทำ 5 นาที | นักเรียนกดทำต่อ กลับตำแหน่งเดิม |
| รอเลือกทางต่อ | ข้อความ "ไม่อยากเรียนแล้ว" | นักเรียนเลือก พักก่อน · ทำต่อแบบง่ายลง · หยุดวันนี้ |
| หยุดเพื่อความปลอดภัย | ข้อความที่สื่อถึงการทำร้ายตนเอง | ครูเป็นคนปลดเท่านั้น |
| Stagnation Deadlock | ส่งซ่อมเสริมครบ 2 รอบแล้วยังติด | ครูสั่ง Manual Override |
| จบชุด | Mastery ของ Target Concept ≥ 0.8 (อย่างน้อย 3 ข้อ) และทำ Main Item ครบหรือทำ Challenge Item ถูก 1 ข้อ · หรือครบ 20 ข้อ (จบ Session พร้อมบันทึกความคืบหน้า) | ไม่มี |

## ผัง 3 · เมื่อกดปุ่มขอคำใบ้

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#EEF3FF", "primaryTextColor": "#1B2530", "primaryBorderColor": "#2A55C6", "lineColor": "#556170", "clusterBkg": "#F6F8FA", "clusterBorder": "#C9D2DC", "titleColor": "#1B2530", "edgeLabelBackground": "#FFFFFF", "fontSize": "15px"}}}%%
flowchart TD
  B(["กดปุ่มขอคำใบ้"]) --> AB{"กดครบ 3 ครั้ง<br/>ภายใน 10 วินาที?"}
  AB -->|"ใช่"| ABX["Hint Abuse<br/>ปุ่มพัก 10 วินาที<br/>ให้คำถามนำแทน<br/>Hint Abuse Index เพิ่มขึ้น"]
  AB -->|"ไม่"| AT{"ข้อนี้ลองตอบ<br/>แล้วหรือยัง?"}
  AT -->|"ยังไม่ตอบ"| T30{"คิดมาแล้ว<br/>30 วินาที?"}
  T30 -->|"ยัง"| W["ยังไม่ปลด<br/>ข้อความ: ลองคิดอีกนิดนะ"]
  T30 -->|"ครบ"| GL1["แสดง L1"]
  AT -->|"ตอบผิดแล้ว"| DD{"อยู่ในช่วง<br/>Deliberate Delay?"}
  DD -->|"ใช่"| WD["บอกเวลาที่เหลือ<br/>ชวนตรวจคำตอบเองก่อน"]
  DD -->|"ไม่"| SQ["คำถามนำ Socratic<br/>ในระดับที่ปลดแล้ว"]
  SQ -.->|"ระดับถัดไปต้องลองตอบใหม่"| NX(["ลองตอบ"])
```

ปุ่มนี้ปลดคำใบ้ระดับใหม่เองไม่ได้ ระดับใหม่ได้จากการลองตอบเท่านั้น คำใบ้ตามบันไดจะขึ้นเองในแผงคำใบ้หลังตอบผิด และระหว่าง Isomorphic Test ปุ่มนี้ถูกซ่อน

## ผัง 4 · AI Tutor สร้างคำใบ้โดยไม่หลุดเฉลย

```mermaid
%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#EEF3FF", "primaryTextColor": "#1B2530", "primaryBorderColor": "#2A55C6", "lineColor": "#556170", "clusterBkg": "#F6F8FA", "clusterBorder": "#C9D2DC", "titleColor": "#1B2530", "edgeLabelBackground": "#FFFFFF", "fontSize": "15px"}}}%%
flowchart LR
  HR["คำขอคำใบ้จากด่าน 3<br/>Item · ระดับคำใบ้ · Error Count<br/>Response Time · แท็กข้อผิดพลาด"]
  CH["ข้อความแชตของนักเรียน"] --> PII["ลบข้อมูลส่วนตัว<br/>เหลือแค่ Student Code"]
  PII --> KW{"Distress Message?<br/>ตรวจในเครื่อง ใช้ได้แม้ Offline"}
  KW -->|"ไม่พบ"| RAG
  KW -->|"เครียดหรือท้อ"| CB["Circuit Breaker<br/>+ Teacher Alert ปกติ"]
  KW -->|"ไม่อยากเรียนแล้ว"| QT["ให้นักเรียนเลือกทางต่อ<br/>+ Teacher Alert ปกติ"]
  KW -->|"สื่อถึงการทำร้ายตนเอง"| SAFE["หยุดทันที · สายด่วน 1323<br/>+ Teacher Alert ด่วน"]
  HR --> RAG["ดึงบริบท RAG<br/>Bug Library ตามแท็ก<br/>ย่อหน้าจากเอกสาร · BM25 + ตัดคำไทย"]
  RAG --> PR["ประกอบ prompt 4 กรอบ<br/>Role · Context · Task · Constraints"]
  PR --> SEL{"Provider<br/>ที่เลือกไว้"}
  SEL -->|"Claude"| CLA["Claude API"]
  SEL -->|"Gemini"| GEM["Gemini API"]
  SEL -->|"Offline"| AH
  CLA -.->|"ล้มเหลว"| GEM
  GEM -.->|"ล้มเหลว"| AH
  CLA --> GD{"Answer-Leak Guard"}
  GEM --> GD
  GD -->|"ไม่มีคำตอบสุดท้าย"| OUT(["แสดงในแผงคำใบ้<br/>บันทึกให้ครูตรวจย้อนหลัง"])
  GD -->|"พบคำตอบสุดท้าย"| AH["Authored Hint<br/>ระดับเดียวกัน"]
  GD -->|"พบรหัส TRIGGER_CIRCUIT_BREAKER"| CB
  AH --> OUT
  classDef care fill:#E9E5F7,stroke:#6A59AE,stroke-width:1.5px
  class CB,QT,SAFE care
```

LLM มีหน้าที่แค่ปรับถ้อยคำ ทุกข้อความต้องผ่าน Answer-Leak Guard ก่อนถึงนักเรียน ถ้าถูกบล็อกหรือ Provider ใช้ไม่ได้ ระบบจะใช้คำใบ้ที่ครูเขียนไว้แทน การตรวจข้อความทุกข์ใจทำในเครื่องก่อนส่งไป Provider จึงทำงานได้แม้ไม่มีอินเทอร์เน็ต ลำดับสำรองเป็นไปตามหน้าตั้งค่าของ Admin ([ADR-0001](adr/0001-authored-hints-and-answer-leak-guard.md))
