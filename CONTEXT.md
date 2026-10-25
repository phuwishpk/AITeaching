# Adaptive Tutor

ระบบติวเตอร์อัจฉริยะ (Intelligent Tutoring System) ที่อ่านร่องรอยการเรียนของนักเรียนแต่ละคน แล้วปรับลำดับโจทย์ ความยาก และคำใบ้ให้อยู่ในเขตพัฒนาการใกล้เคียง (ZPD) โดยไม่เฉลยคำตอบ และให้ครูเป็นผู้ตัดสินใจขั้นสุดท้ายเสมอ

## Language

### เนื้อหา (Domain Model)

**Subject** (วิชา):
วิชาที่ครูสร้างขึ้นในระบบ มี Knowledge Map ของตัวเองและมี Question Set ได้หลายชุด
_Avoid_: Course

**Concept** (มโนทัศน์):
หน่วยความรู้หนึ่งเรื่องที่ระบบวัดความชำนาญแยกได้ เช่น "แก้สมการสองขั้น"
_Avoid_: Topic, Skill, บทเรียน

**Target Concept** (มโนทัศน์เป้าหมาย):
Concept ที่ Question Set หนึ่งชุดต้องการให้นักเรียนทำได้

**Prerequisite Concept** (ความรู้พื้นฐานที่ต้องรู้ก่อน):
Concept ที่นักเรียนต้องเข้าใจก่อนจึงจะเรียน Concept อื่นได้
_Avoid_: Basic concept, พื้นฐาน

**Knowledge Map** (โครงข่ายความรู้):
แผนผังของ Concept ทั้งหมดใน Subject และเส้นเชื่อม Prerequisite ระหว่างกัน
_Avoid_: Network of Concepts, Concept map

**Question Set** (ชุดคำถาม):
ชุดโจทย์ที่มี Target Concept หนึ่งตัว ประกอบด้วย Main Item, Isomorphic Item, Remedial Item และ Challenge Item นักเรียนเข้าทำทีละชุด
_Avoid_: Module, Lesson, Quiz, แบบทดสอบ (สื่อว่าเป็นการสอบเก็บคะแนน)

**Item** (โจทย์):
คำถามหนึ่งข้อที่นักเรียนต้องส่งคำตอบ แต่ละข้อวัด Concept เดียว
_Avoid_: Question (ชนกับ Socratic Question), Problem, Exercise

**Main Item** (โจทย์หลัก):
Item ที่วัด Target Concept ของ Question Set โดยตรง

**Challenge Item** (โจทย์ท้าทาย):
Item ที่ยากกว่าระดับปกติของ Target Concept ใช้ในเส้นทาง Fast-Track

**Isomorphic Item** (โจทย์คู่ขนาน):
Item ที่มีโครงสร้างและ Concept เดียวกับอีกข้อหนึ่ง แต่เปลี่ยนตัวเลขหรือบริบท
_Avoid_: Parallel item, โจทย์ซ้ำ

**Remedial Item** (โจทย์ปูพื้นฐาน):
Item ของ Prerequisite Concept ที่ใช้ใน Remedial Loop
_Avoid_: โจทย์ซ่อม

**Walkthrough Example** (ตัวอย่างทีละขั้น):
ตัวอย่างที่แสดงวิธีทำครบทุกขั้นพร้อมคำอธิบาย นักเรียนอ่านอย่างเดียวโดยไม่ต้องส่งคำตอบ และไม่ใช่เฉลยของข้อที่นักเรียนกำลังทำ
_Avoid_: Solution, เฉลย

**Answer Format** (รูปแบบคำตอบ):
วิธีที่นักเรียนตอบ Item และระบบตรวจ ได้แก่ ปรนัย ตัวเลข และข้อความสั้น
_Avoid_: Question type

**Bug Library** (คลังข้อผิดพลาด):
ชุดรูปแบบคำตอบผิดที่รู้จักแล้ว แต่ละรายการระบุว่าเป็น Slip หรือ Misconception วิธีตอบสนอง และ Prerequisite Concept ที่เกี่ยวข้องถ้ามี
_Avoid_: Error database, คลังคำตอบผิด

**Slip** (ความสะเพร่า):
คำตอบผิดจากความพลั้งเผลอของนักเรียนที่เข้าใจ Concept นั้นแล้ว
_Avoid_: Careless mistake, Error

**Misconception** (ความเข้าใจผิดเชิงมโนทัศน์):
คำตอบผิดที่มาจาก "ทฤษฎีส่วนตัวที่ผิด" ของนักเรียนเกี่ยวกับกฎหรือโครงสร้างของ Concept
_Avoid_: Bug, Misunderstanding

**Unclassified** (ยังไม่จำแนก):
คำตอบผิดที่ไม่เข้าเกณฑ์ทั้ง Slip และ Misconception

**AI-Suggested Tag** (แท็กที่ AI เดา):
แท็กจาก Bug Library ที่ LLM เสนอให้คำตอบ Unclassified ใช้ปรับถ้อยคำคำใบ้ได้ แต่ไม่มีผลต่อระดับคำใบ้และสถิติของครูจนกว่าครูจะยืนยัน

**Authored Hint** (คำใบ้ต้นฉบับ):
คำใบ้ที่ครูเขียนไว้ล่วงหน้าสำหรับแต่ละ Item และแต่ละ Hint Level ถือเป็นข้อมูลอ้างอิงหลักของคำใบ้ทั้งหมด
_Avoid_: Template hint, คำใบ้สำรอง

**Source Document** (เอกสารวิชา):
เอกสารที่ครูอัปโหลดให้ AI Tutor ใช้อ้างอิงเนื้อหาของ Subject
_Avoid_: File, Material, ไฟล์แนบ

**Readiness Check** (การตรวจความพร้อม):
การตรวจ Question Set ก่อนเปิดใช้ว่ามีองค์ประกอบครบตามที่ตรรกะของระบบต้องใช้

**Gem** (เจม):
บทเรียนที่ครูสร้างแบบ Gemini Gem จากชื่อ คำอธิบาย Gem Instructions, Starter Tools และ Knowledge File แล้ว LLM สร้าง Item Bank ให้ ข้างในระบบ Gem หนึ่งตัวคือ Subject หนึ่งวิชากับ Question Set หนึ่งชุด
_Avoid_: Bot, Assistant, AI Draft

**Gem Instructions** (คำสั่งของ Gem):
ข้อความที่ครูเขียนกำหนดบุคลิกและวิธีสอนของ Gem ใช้เป็นกรอบ Role & Persona และกฎเพิ่มเติมของครู แก้ Constraints & Fallback ไม่ได้
_Avoid_: System prompt (prompt ที่ส่งจริงรวม 4 กรอบ)

**Starter Tools** (เครื่องมือเริ่มต้น):
สวิตช์แชตของ Gem และ Starter Prompt เครื่องมือการสอนอื่น (คำใบ้, Isomorphic Test, Walkthrough, ทบทวนพื้นฐาน) มาจาก Flow ที่ออกแบบจากคำสั่งของครู ไม่มีสวิตช์แยก

**Starter Prompt** (คำถามเริ่มต้น):
ปุ่มคำถามที่ครูเตรียมไว้ให้นักเรียนกดถามครูผู้ช่วยได้ทันที

**Knowledge File** (ไฟล์ความรู้):
Source Document ที่แนบกับ Gem ตัวใดตัวหนึ่ง ใช้ทั้งตอนสร้าง Item Bank และตอน RAG ค้นระหว่างสอน

**Item Bank** (คลังโจทย์):
Knowledge Map, Item, Authored Hint, Bug Library และ Walkthrough Example ทั้งหมดที่ LLM สร้างให้ Gem ครูตรวจและแก้ได้
_Avoid_: Question pool

**Answer Key** (เฉลยแบบมีโครงสร้าง):
Answer Format, คำตอบที่ถูก และคำตอบที่ยอมรับของ Item หนึ่งข้อ engine ใช้ตรวจคำตอบด้วยกฎ

**Answer Key Check** (การตรวจเฉลย):
การตรวจ Answer Key ที่ LLM สร้าง สองชั้น คือ LLM แก้โจทย์ซ้ำโดยไม่เห็นเฉลย และ sympy คำนวณเฉลยจริงเมื่อเป็นสมการหรือเลขคณิต

**Flagged Item** (โจทย์ติดธง):
Item ที่ไม่ผ่าน Answer Key Check ไม่ถูกส่งให้นักเรียนจนกว่าครูจะยืนยันหรือแก้

**Live Generation** (การสร้างโจทย์สด):
การให้ LLM สร้าง Item เพิ่มระหว่างเรียนเมื่อ Item Bank ใกล้หมดหรือต้องการ Isomorphic Item เพิ่ม มีเพดานต่อนักเรียนต่อ Session

**Gem Version** (เวอร์ชันของ Gem):
สำเนาของ Gem ที่เกิดทุกครั้งที่ครูบันทึก Session หนึ่งใช้ Gem Version เดียวตั้งแต่เริ่มจนจบ

**Gem Flow** (Flow การสอนของ Gem):
ลำดับการสอนที่ LLM ออกแบบจาก Gem Instructions เป็นขั้นและเส้นที่มีเงื่อนไข ครูตรวจและแก้ได้ Gem ที่ไม่มี Gem Flow ใช้ Standard Template
_Avoid_: ผังของ Gem (ใช้กับภาพที่วาด ไม่ใช่ตัว Flow)

**Flow Step** (ขั้นของ Flow):
หนึ่งขั้นใน Gem Flow จากคลังขั้นที่ engine รันได้ เช่น ทำโจทย์ คำใบ้ บทเรียนย่อ อธิบายความคิด พัก แจ้งครู หยุดรอครู ด่านตัดสินใจ จบ

**Edge Condition** (เงื่อนไขบนเส้น):
กฎที่อ่านได้บนเส้นของ Gem Flow เขียนจากตัวแปรของ Student Model engine ใช้เส้นแรกที่เป็นจริง

**Locked Invariant** (สิ่งที่ล็อกไว้ทุก Flow):
กลไกที่ทำงานทุก Gem Flow และไม่อยู่ในกราฟ ได้แก่ การตรวจด้วยกฎและ Answer-Leak Guard, หยุดเมื่อทำร้ายตนเองและ Manual Override, Data Cleaning และ Rapid Guess, Idle Pause และเพดานจำนวนข้อ

**Standard Template** (ผังมาตรฐาน):
ผังตรรกะเดิมของระบบ (3 ด่าน บันไดคำใบ้ Isomorphic Test Remedial Loop) ที่ Stress Test สถานการณ์สาธิต และหน้ากฎอธิบาย

### นักเรียนและร่องรอย (Student Model)

**Student** (นักเรียน):
บุคคลที่ทำ Question Set ในระบบ ระบบรู้จักนักเรียนผ่าน Student Code เท่านั้น
_Avoid_: Learner (ใช้ได้เฉพาะในชื่อที่มาจาก outline หรือสเปก เช่น Target Learners และ Fast Learners), User

**Student Code** (รหัสนักเรียนในระบบ):
รหัสนามแฝงที่ใช้แทนชื่อจริงในข้อมูลทุกส่วนของระบบ
_Avoid_: Learner Code, รหัสประจำตัวนักเรียน (รหัสของโรงเรียนยังระบุตัวบุคคลได้)

**Roster** (บัญชีรายชื่อ):
ตารางจับคู่ Student Code กับชื่อจริง เก็บแยกจากข้อมูลการเรียน และมีแค่ครูที่เปิดดูได้
_Avoid_: Student list, User table

**Digital Trace** (ร่องรอยดิจิทัล):
บันทึกเหตุการณ์หนึ่งรายการ ประกอบด้วย [วัน-เวลา] + [Student Code] + [การกระทำ] + [วัตถุเป้าหมายบนหน้าจอ]
_Avoid_: Log, Click

**Session** (เซสชัน):
ช่วงเวลาที่นักเรียนทำ Question Set ต่อเนื่องหนึ่งครั้ง ตั้งแต่เข้าทำจนออกหรือระบบจบ Session
การจบ Session คือการหยุดเรียนรอบนี้ก่อนถึงเป้าหมาย (ครบเพดานจำนวนข้อ นักเรียนเลือกหยุด ครูสั่งจบ หรือโจทย์หมด) ความคืบหน้ายังอยู่ครบ และนักเรียนกลับมาเริ่ม Session ใหม่ต่อจากเดิมได้ ไม่ใช่การสอบตก
_Avoid_: Visit, Login

**Set Completion** (จบชุด):
นักเรียนเรียนรู้ Question Set นั้นครบตามเป้าหมายแล้ว คือ Mastery ของ Target Concept ถึงเกณฑ์จากโจทย์มากพอ และทำโจทย์หลักครบหรือทำโจทย์ท้าทายได้ ต่างจากการจบ Session ที่แค่หยุดพักกลางทาง
_Avoid_: Finish, Pass

**Attempt** (การส่งคำตอบ):
การส่งคำตอบที่ถูกรูปแบบหนึ่งครั้งใน Item หนึ่งข้อ คำตอบที่ผิดรูปแบบไม่นับเป็น Attempt
_Avoid_: Try, Submission

**Error Count** (จำนวนครั้งที่ผิด):
จำนวน Attempt ที่ผิดใน Item ปัจจุบัน นับแยกทีละข้อ ไม่นับ Rapid Guess และเริ่มนับใหม่เมื่อขึ้นข้อใหม่หรือกลับมาจาก Remedial Loop
_Avoid_: จำนวนครั้งที่ผิดในเรื่องเดิม (ภาพรวมระดับ Concept ใช้ Mastery)

**Response Time** (เวลาคิด):
จำนวนวินาทีตั้งแต่ช่องตอบพร้อมใช้จนถึงส่ง Attempt ไม่รวมช่วงที่ถูกล็อก
_Avoid_: Latency, เวลาตอบสนอง

**First Attempt Success** (ถูกตั้งแต่ครั้งแรก):
การที่นักเรียนตอบ Item ถูกใน Attempt แรกโดยไม่ใช้คำใบ้

**Item Accuracy** (อัตราตอบถูก):
สัดส่วนข้อที่ตอบถูกแบบไม่ถ่วงน้ำหนัก ใช้เป็นตัวแปรนำเข้า ไม่ใช่ระดับความชำนาญ

**Content Revisit** (การย้อนดูเนื้อหา):
จำนวนครั้งที่นักเรียนกลับไปเปิดดูเนื้อหาที่ผ่านมาแล้ว

**Hint Abuse Index** (ดัชนีการปั๊มคำใบ้):
ค่าที่บอกว่านักเรียนกดขอคำใบ้ซ้ำโดยไม่ลองตอบบ่อยเพียงใด

**Mastery** (ระดับความชำนาญ):
ค่าความชำนาญของนักเรียนต่อ Concept หนึ่ง คิดจากผลของ Item ล่าสุดหลายข้อ โดยถ่วงน้ำหนักตามความช่วยเหลือที่ใช้
_Avoid_: Score, คะแนน, Item Accuracy

**Mastery Bar** (แถบความชำนาญ):
การแสดง Mastery ให้นักเรียนเห็นแบบไม่มีตัวเลขและไม่มีสีเตือน มาพร้อมข้อความเชิงบวกเสมอ
_Avoid_: Progress Bar (สื่อว่าทำไปแล้วกี่ข้อ ซึ่งเป็นคนละความหมาย)

**Risk Score** (คะแนนความเสี่ยง):
ค่าประเมินโอกาสที่นักเรียนจะเลิกเรียน (Drop-out) แสดงเฉพาะฝั่ง Teacher และ Admin ไม่แสดงต่อนักเรียน
_Avoid_: Fail probability, เปอร์เซ็นต์สอบตก

**Student Cluster** (กลุ่มพฤติกรรมนักเรียน):
กลุ่มที่ระบบจัดนักเรียนเข้าไปตามรูปแบบพฤติกรรมการเรียน ไม่แสดงต่อนักเรียน ชื่อกลุ่มทั้ง 4 คงไว้ตามสเปก เช่น Fast Learners และ Bite-sized Users
_Avoid_: Level, ระดับนักเรียน (กลุ่มพฤติกรรมไม่ได้เรียงเก่ง-อ่อน)

**Burnout Signal** (สัญญาณหมดไฟ):
รูปแบบพฤติกรรมที่บ่งชี้ว่านักเรียนอาจหมดไฟ เช่น Idle Pause ซ้ำหลายครั้ง หรือ Rapid Guess ติดกัน ระบบแจ้งครูแบบเงียบโดยไม่หยุดกิจกรรมและไม่บอกนักเรียน

**Simulated Cohort** (กลุ่มนักเรียนจำลอง):
นักเรียนสมมติที่สร้างขึ้นเพื่อให้แดชบอร์ดมีข้อมูลระดับห้องเรียน ต้องติดป้ายว่าเป็นข้อมูลจำลองทุกครั้งที่แสดง
_Avoid_: Mock data, Fake students

### การสอน (Pedagogical Model)

**Learning Path** (เส้นทางการเรียน):
ทางที่ระบบเลือกให้นักเรียนหลังตอบถูก มี 3 แบบ คือ Fast-Track, Standard Flow และ Supported Flow

**Fast-Track**:
Learning Path ที่ข้ามโจทย์พื้นฐานไปยัง Challenge Item เมื่อ Mastery สูงและตอบเร็ว

**Standard Flow**:
Learning Path ปกติตามลำดับใน Knowledge Map

**Supported Flow**:
Learning Path ที่ลดความยากลงหนึ่งขั้นเมื่อ Mastery ต่ำ

**Flow Position** (ตำแหน่งในผัง):
สถานะปัจจุบันของนักเรียนหนึ่งคนในตรรกะของระบบ มีชื่อเรียกชัดเจน เช่น Deliberate Delay, Remedial Loop รอบ 1 หรือ Circuit Breaker นักเรียนหนึ่งคนอยู่ได้ทีละตำแหน่ง
_Avoid_: Flow State (ชนกับทฤษฎี Flow ของ Csikszentmihalyi), Status, Stage

**Decision Trace** (ร่องรอยการตัดสินใจ):
บันทึกเหตุผลของการเปลี่ยน Flow Position แต่ละครั้ง ระบุกฎ ค่าตัวแปร และผลวินิจฉัยที่ใช้ตัดสิน
_Avoid_: Log, Audit log (ใช้เรียกบันทึก Manual Override)

**Hint Ladder** (บันไดคำใบ้):
คำใบ้ 3 ระดับที่ปลดทีละขั้นตามความพยายามของนักเรียน ไม่มีระดับใดบอกคำตอบสุดท้าย
_Avoid_: Scaffolding (เป็นชื่อแนวคิดการสอน ไม่ใช่ชื่อกลไก), Help

**Hint Level 1 · Prompting** (คำใบ้สะกิดความคิด):
คำใบ้ที่ชี้จุดสังเกตหรือชวนให้ตรวจทาน

**Hint Level 2 · Rule Explanation** (คำใบ้อธิบายกฎ):
คำใบ้ที่สรุปกฎหรือหลักการที่เกี่ยวข้องสั้น ๆ

**Hint Level 3 · Bottom-out Hint** (คำใบ้ชี้นำขั้นแรก):
คำใบ้ที่แสดงวิธีทำเฉพาะขั้นแรก แล้วให้นักเรียนทำต่อเอง

**Hint Floor** (ระดับคำใบ้ขั้นต่ำ):
ระดับคำใบ้ต่ำสุดที่นักเรียนได้รับตามผลวินิจฉัยจาก Bug Library เช่น Misconception เริ่มที่ Hint Level 2 แม้เพิ่งผิดครั้งแรก

**Socratic Question** (คำถามนำ):
คำถามที่ชวนนักเรียนคิดขั้นถัดไปเองโดยไม่บอกคำตอบ

**Deliberate Delay** (การหน่วงเวลาโดยตั้งใจ):
ช่วงรอหลังตอบผิดครั้งแรก ก่อนระบบปลดคำใบ้ เพื่อให้นักเรียนได้กำกับตนเอง
_Avoid_: Cooldown, Lock (การล็อกเป็นของ Rapid Guess)

**Isomorphic Test** (ด่านทดสอบคู่ขนาน):
การให้ทำ Isomorphic Item โดยปิดคำใบ้ทั้งหมด หลังนักเรียนผ่าน Item ก่อนหน้าด้วยความช่วยเหลือของคำใบ้

**Gaming the System** (การหาช่องโกงระบบ):
คำรวมของพฤติกรรมที่พยายามได้คำตอบโดยไม่คิดเอง ได้แก่ Rapid Guess และ Hint Abuse

**Rapid Guess** (การเดาสุ่ม):
Attempt ที่ผิดและส่งเร็วกว่าเวลาอ่านขั้นต่ำของ Item ระบบปรับคะแนนข้อนั้นเป็นโมฆะ
_Avoid_: Spam, กดมั่ว

**Hint Abuse** (การปั๊มคำใบ้):
การกดขอคำใบ้ซ้ำติดกันในเวลาสั้นโดยไม่ลองตอบ เพื่อหวังเห็นคำตอบ

**Impasse** (ภาวะติดหล่มความคิด):
ภาวะที่นักเรียนคิดต่อเองไม่ได้แล้ว ได้แก่ ผิดครั้งที่ 3 โดยเวลาคิดยาวขึ้นต่อเนื่อง, ยังผิดหลังได้ Hint Level 3 หรือไม่ผ่าน Isomorphic Test 2 รอบติดกันใน Concept เดียว
_Avoid_: Stuck, Circuit Breaker (เป็นคนละกลไก)

**Remedial Loop** (ลูปซ่อมเสริม):
การพัก Item ที่เกิด Impasse ไว้ก่อน ให้ทำ Remedial Item จนผ่าน แล้วจึงกลับไปทำ Item เดิม นับเป็นรอบต่อ Item
_Avoid_: Remediation, การซ่อมเสริม

**Distress Message** (ข้อความสัญญาณทุกข์ใจ):
ข้อความแชตที่สื่อถึงความเครียด ความท้อ หรือความต้องการเลิกเรียน ข้อความที่สื่อถึงการทำร้ายตนเองถือเป็นระดับรุนแรงที่สุด

**Circuit Breaker** (การตัดวงจร):
การหยุดกิจกรรมทั้งหมดชั่วคราวเพื่อดูแลสภาพจิตใจนักเรียน ให้พักสายตาแล้วเริ่มใหม่ด้วย Walkthrough Example
_Avoid_: Lockout, Impasse

**Stagnation Deadlock** (ทางตันการซ่อมเสริม):
สถานะที่ Item หนึ่งถูกส่งเข้า Remedial Loop ครบ 2 รอบแล้วยังไม่ผ่าน ระบบหยุดลูปและส่งเรื่องให้ครู
_Avoid_: Deadlock, Failure

**Idle Pause** (การพักเมื่อหน้าจอนิ่ง):
การพักบทเรียนอัตโนมัติเมื่อนักเรียนไม่มีการกระทำนานเกินกำหนด พร้อมข้อความปลอบใจ
_Avoid_: Timeout, Session expired

**Cross-Format Check** (การตรวจความสอดคล้องข้ามรูปแบบโจทย์):
การเทียบผลของ Concept เดียวกันระหว่าง Answer Format ต่างชนิด เช่น ปรนัยกับเติมคำ ถ้าผลขัดกัน ระบบลด Mastery ลง
_Avoid_: Cross-Validation (ในบท ML หมายถึงการแบ่งข้อมูลเพื่อทดสอบโมเดล)

### AI Tutor

**AI Tutor** (ครูผู้ช่วย AI):
บทบาทที่ใช้ LLM ปรับถ้อยคำคำใบ้ให้เข้ากับนักเรียนแต่ละคนและตอบแชตแบบ Socratic ภายใต้ Context Framing
_Avoid_: Chatbot, LLM (LLM คือโมเดล ส่วน AI Tutor คือบทบาท)

**Context Framing** (การตีกรอบบริบท):
กรอบ 4 ข้อที่ใช้กำกับ LLM ทุกครั้ง ได้แก่ Role & Persona, Context & Environment, Task & Intent และ Constraints & Fallback

**Answer-Leak Guard** (ด่านกันเฉลยหลุด):
ด่านที่ตรวจทุกข้อความจาก LLM ก่อนถึงนักเรียน ถ้าพบคำตอบสุดท้ายจะใช้ Authored Hint แทน
_Avoid_: Filter, Moderation

**Provider** (ผู้ให้บริการ LLM):
บริการ LLM ภายนอกที่ AI Tutor เรียกใช้ได้ ได้แก่ Claude และ Gemini
_Avoid_: Model (โมเดลเป็นตัวเลือกย่อยภายใน Provider), Vendor

**Offline Mode** (โหมดออฟไลน์):
โหมดที่ AI Tutor ใช้เฉพาะ Authored Hint โดยไม่เรียก Provider ใดเลย สร้าง Gem และ Live Generation ไม่ได้ในโหมดนี้

**AI Outage** (AI ขัดข้อง):
สถานะที่ Provider เรียกไม่สำเร็จระหว่างเรียน ระบบหยุดเฉพาะเมื่อขั้นนั้นขาด AI ไม่ได้ (Live Generation ล้มและคลังหมด) แล้วลองใหม่เองเป็นระยะ

### บทบาทและการควบคุม (Human-in-the-Loop)

**Teacher** (ครู):
ผู้สอนที่สร้างและแก้ Gem ดูแลนักเรียนรายคน เห็น Roster, Risk Score และ Teacher Alert และสั่ง Manual Override ได้
_Avoid_: Instructor

**Admin** (ผู้ดูแลระบบ):
ผู้ที่ดู flow ที่ครูออกแบบใน Gem แต่ละตัวและการทำงานภายในของระบบ ตั้งค่าระบบและ API key เห็น Flow Position, Decision Trace และตัวแปรทุกตัวผ่าน Student Code แต่ไม่เห็น Roster และแก้ Gem ไม่ได้
_Avoid_: Super user, Developer

**Manual Override** (การแทรกแซงโดยครู):
คำสั่งของครูที่มีผลเหนือการตัดสินใจอัตโนมัติทุกอย่าง เช่น หยุดระบบ เปลี่ยนโจทย์ หรือแก้สถานะนักเรียน

**Teacher Alert** (การแจ้งเตือนครู):
ข้อความที่ระบบส่งให้ครูเมื่อถึงจุดที่มนุษย์ต้องตัดสินใจ มี 3 ระดับ คือ ด่วน ปกติ และเงียบ (แสดงบนแดชบอร์ดโดยไม่เด้งเตือน)

**Alert Rule** (กฎแจ้งเตือนของ Gem):
การตั้งค่าต่อ Gem ว่าสถานการณ์ใดส่ง Teacher Alert ระดับใด และโหมด "แจ้งอย่างเดียว" หรือ "หยุดรอครู" สถานการณ์ทำร้ายตนเองปิดไม่ได้และหยุดรอครูเสมอ

**Principle Card** (การ์ดหลักการ):
การ์ดในหน้า Admin ที่อธิบายแนวคิดเบื้องหลังขั้นตอนหนึ่ง พร้อมที่มาในสเปกและตำแหน่งในโค้ดที่ทำหน้าที่นั้น

**Demo Mode** (โหมดสาธิต):
โหมดที่ย่อเวลาของกลไกต่าง ๆ และเปิดให้เล่น Scenario ซ้ำ ใช้ระหว่างสาธิตเท่านั้น
_Avoid_: โหมดนำเสนอ (เป็นชื่อของ Presentation View)

**Presentation View** (มุมมองนำเสนอ):
การแสดงหน้า Admin แบบขยายตัวอักษรและซ่อนปุ่มตั้งค่า ใช้ตอนฉายขึ้นจอ
