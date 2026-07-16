// All human-readable copy, in both languages, in ONE place (SPEC-03 §9).
//
// WHY A DATA MODULE AND NOT MARKUP:
//   * The hybrid layout renders the SAME mode copy TWICE -- the contextual "how
//     do I trigger a fall here?" card (for a student mid-experiment) and the
//     comparison block (for an instructor reading the whole picture at a glance).
//     Two copies in HTML would drift the first time someone edits one.
//   * index.html would blow past CLAUDE.md's 500-line limit with 3 modes x 8
//     fields x 2 languages inlined.
//   * Translation is reviewable here as prose, without hunting through tags.
//
// AUDIENCE. Two, deliberately, and they need different things:
//   * STUDENTS run the experiment. They need "what do I physically DO to make it
//     say FALL?" -- imperative, short, at the moment of need.
//   * INSTRUCTORS / management read the comparison and must be able to teach the
//     project's point WITHOUT reading any code. Jeffry's words: his boss knows
//     the bird's-eye view only.
//
// LANGUAGE: 繁體中文 as used in TAIWAN (台灣用語) -- 資料 not 数据, 影像 not 视频,
// 模式 not 模組. Default is English (Jeffry's call); the toggle is in the header.

// --- chrome + instrument labels ----------------------------------------

export const UI = {
  en: {
    appTitle: "Edge Sensing — Live",
    langBtn: "中文",
    themeDark: "dark",
    themeLight: "light",
    reset: "reset totals",
    connected: "connected",
    connecting: "connecting…",
    unreachable: "relay unreachable — retrying",
    noData: "no data",
    modeLive: (m) => `▶ Mode ${m} live`,

    status: "Status",
    waiting: "waiting…",
    motion: "motion",
    audio: "audio",
    blobs: "blobs",
    fall: "fall",
    posture: "posture",

    tuning: "Fall sensitivity",
    tuningLive: "live",
    loudThreshold: "loud threshold",
    motionThreshold: "motion threshold",
    tuneHint: "Lower <b>loud</b> so quieter sounds count. Raise <b>motion</b> so a " +
      "small movement still reads as “stopped”. Applies to Mode 1 instantly and " +
      "Modes 2/3 within a second — the Jetson keeps deciding, the dashboard just " +
      "feeds the numbers.",

    chart: "Last 60 seconds",
    ago60: "60s ago",
    now: "now",
    events: "Events",
    noEvents: "no events yet",

    video: "What the relay can see",
    noImage: "no image",
    waitingData: "waiting for data…",

    lesson: "The lesson — bandwidth",
    ratioBoth: "more data sent by Mode 1 than Mode 2",
    ratioSwitch: "now switch to Mode 2 to see the ratio",
    ratioNone: "run both modes to see the ratio",
    previewRow: "setup camera",

    // The setup preview (SPEC-08 Part B)
    showCamera: "show camera (setup)",
    hideCamera: "hide camera",
    // No leading ⚠ -- nve-alert draws its own icon and the two rendered as "⚠ ⚠".
    previewBanner: "Pixels are leaving the device — setup only. This is what " +
      "Mode 1 does every second. Turn it off and watch the number collapse.",

    // The teaching blocks
    howToFall: "How to trigger FALL",
    inThisMode: (m) => `in Mode ${m}`,
    pickAMode: "Pick a mode above to see how to trigger a fall in it.",
    compareTitle: "The three modes — what, why, and what each one costs",
    compareLead: "Same camera. Same room. Same question: “has someone fallen?” " +
      "The only thing that changes is WHERE the thinking happens — and that " +
      "changes everything else.",
    colWhat: "What it does",
    colWhy: "Why you would",
    colSenses: "Senses",
    colHow: "Make it say FALL",
    colPros: "Good",
    colCons: "Bad",
    multimodalTitle: "About the sound",
    multimodal: "This workshop is <b>multi-modal</b>: two different senses, not " +
      "one. <b>Modes 1 and 2 need both</b> — their rule is “a loud noise AND the " +
      "movement stopped”, so neither sense alone can raise the alarm. <b>Mode 3 " +
      "does not need sound at all</b> — it can see you are lying on the floor. " +
      "It listens anyway, and a thump makes it fire in 1 second instead of 3. " +
      "That is what fusion really buys: not permission, but <b>confidence, " +
      "sooner</b>. A silent collapse still raises the alarm — which is exactly " +
      "why sound must never be a requirement.",
  },

  zh: {
    appTitle: "邊緣感測 — 即時",
    langBtn: "EN",
    themeDark: "深色",
    themeLight: "淺色",
    reset: "重設累計",
    connected: "已連線",
    connecting: "連線中…",
    unreachable: "無法連線到中繼站 — 重試中",
    noData: "尚無資料",
    modeLive: (m) => `▶ 模式 ${m} 執行中`,

    status: "狀態",
    waiting: "等待中…",
    motion: "動作",
    audio: "聲音",
    blobs: "區塊",
    fall: "跌倒",
    posture: "姿態",

    tuning: "跌倒靈敏度",
    tuningLive: "即時",
    loudThreshold: "音量門檻",
    motionThreshold: "動作門檻",
    tuneHint: "調低<b>音量門檻</b>，較小的聲音也會被算進去。調高<b>動作門檻</b>，" +
      "輕微的移動也會被視為「停止」。模式 1 立即生效，模式 2／3 會在一秒內生效 —— " +
      "判斷始終在 Jetson 上進行，儀表板只負責提供數值。",

    chart: "最近 60 秒",
    ago60: "60 秒前",
    now: "現在",
    events: "事件紀錄",
    noEvents: "尚無事件",

    video: "中繼站看得到什麼",
    noImage: "沒有影像",
    waitingData: "等待資料…",

    lesson: "重點 — 頻寬用量",
    ratioBoth: "模式 1 送出的資料量是模式 2 的倍數",
    ratioSwitch: "切換到模式 2 即可看到倍數",
    ratioNone: "執行兩種模式即可看到倍數",
    previewRow: "校正用攝影機",

    showCamera: "顯示攝影機（校正用）",
    hideCamera: "關閉攝影機",
    previewBanner: "影像正在離開裝置 —— 僅供校正使用。模式 1 每一秒都在做這件事。" +
      "把它關掉，看看數字如何直接掉下來。",

    howToFall: "如何觸發「跌倒」",
    inThisMode: (m) => `模式 ${m}`,
    pickAMode: "請先在上方選擇模式，這裡會顯示該模式的觸發方式。",
    compareTitle: "三種模式 — 是什麼、為什麼、各自的代價",
    compareLead: "同一台攝影機、同一個房間、同一個問題：「有人跌倒了嗎？」" +
      "唯一改變的只有「在哪裡思考」—— 而這一點改變了其他所有事情。",
    colWhat: "這是什麼",
    colWhy: "為什麼這樣做",
    colSenses: "使用的感測器",
    colHow: "如何觸發「跌倒」",
    colPros: "優點",
    colCons: "缺點",
    multimodalTitle: "關於「聲音」",
    multimodal: "本工作坊的主題是<b>多模態</b>：使用兩種不同的感測，而不是一種。" +
      "<b>模式 1 和模式 2 兩種都需要</b> —— 它們的規則是「有巨大聲響<b>而且</b>" +
      "動作停止了」，所以單靠任何一種感測都無法發出警報。<b>模式 3 則完全不需要聲音</b>" +
      " —— 它看得出你正躺在地上。但它仍然會聽：若同時聽到撞擊聲，警報會在 1 秒內發出，" +
      "而不是 3 秒。這才是「融合」真正的價值：它買到的不是「許可」，而是<b>更快的把握</b>。" +
      "無聲的倒下依然會觸發警報 —— 這正是聲音絕對不能成為必要條件的原因。",
  },
};

// Flag words arrive from the relay as DATA (`person-active`, `quiet`, `FALL?`).
// Translated for display only -- the wire protocol stays English, or the relay
// and the dashboard would disagree about what a flag means (SPEC-01 §4).
export const FLAGS = {
  en: { "FALL?": "FALL?", "person-active": "person-active", "quiet": "quiet" },
  zh: { "FALL?": "疑似跌倒！", "person-active": "有人活動", "quiet": "安靜" },
};

// What the video panel says about where the pixels came from -- the privacy
// lesson in one line, per mode.
export const PROVENANCE = {
  en: {
    1: "Mode 1 sends every pixel — the relay decodes them to find motion.",
    2: "Mode 2 computed the features on the Jetson and sent ~200 bytes. Raw pixels never left the device.",
    3: "Mode 3 ran MoveNet on the Jetson. The skeleton is drawn from ~600 bytes of coordinates — no pixel of you crossed the LAN.",
  },
  zh: {
    1: "模式 1 送出每一個像素 —— 由中繼站解碼後再找出動作。",
    2: "模式 2 在 Jetson 上算完特徵，只送出約 200 位元組。原始影像從未離開裝置。",
    3: "模式 3 在 Jetson 上執行 MoveNet。這個骨架是用約 600 位元組的座標畫出來的 —— 你的影像沒有任何一個像素經過區域網路。",
  },
};

export const WHY_BLANK = {
  en: { 2: "Mode 2 sent no image — only a feature vector",
        3: "Mode 3 sent no image — only a skeleton" },
  zh: { 2: "模式 2 沒有送出影像 —— 只有一組特徵數值",
        3: "模式 3 沒有送出影像 —— 只有一副骨架" },
};

// --- the three modes ----------------------------------------------------
//
// `how` is the field this whole feature exists for. Jeffry's complaint was that
// reaching FALL was ambiguous, so students could not experiment on their own.
// Keep these IMPERATIVE and PHYSICAL -- what to do with your body, not how the
// code works.

export const MODE_INFO = {
  1: {
    en: {
      name: "Mode 1 — send everything",
      tagline: "The camera is dumb. The laptop thinks.",
      senses: "camera + microphone",
      what: "The Jetson sends every pixel and every sound to the laptop, about " +
        "583 KB every second. The laptop decodes the pictures and does all the " +
        "thinking. The Jetson understands nothing.",
      why: "This is how most cameras have always worked, and it is the easiest " +
        "thing to build: the device is just a camera. All the cleverness lives " +
        "in one place you control, and you keep the raw footage.",
      how: [
        "Make a loud noise — clap hard, or drop a book.",
        "Then STOP MOVING and stay still for a second or two.",
        "The rule is: a loud sound AND the movement stopped.",
        "Both are required — clapping while you keep moving will not fire.",
      ],
      pros: [
        "Simplest possible device — no AI on the edge",
        "Change the algorithm any time; nothing to redeploy",
        "You keep the raw video for later analysis",
        "The laptop can double-check anything it saw",
      ],
      cons: [
        "~583 KB/s — one camera saturates a cheap network",
        "Your face leaves the room and travels the LAN",
        "Network drops = those seconds are gone forever",
        "100 cameras = 100× the bandwidth. It does not scale",
      ],
    },
    zh: {
      name: "模式 1 — 全部送出",
      tagline: "攝影機不思考，由筆電負責思考。",
      senses: "攝影機 + 麥克風",
      what: "Jetson 把每一個像素和每一個聲音都送到筆電，每秒約 583 KB。" +
        "由筆電解碼影像並完成所有判斷。Jetson 本身什麼也不理解。",
      why: "大多數攝影機一直以來都是這樣運作的，而且這是最容易做出來的方式：" +
        "裝置就只是一台攝影機。所有的智慧都集中在你能掌控的同一個地方，而且原始影像會被保留下來。",
      how: [
        "製造一個很大的聲響 —— 用力拍手，或把書本掉到地上。",
        "接著「停止動作」，靜止一到兩秒。",
        "規則是：有巨大聲響「而且」動作停止了。",
        "兩者缺一不可 —— 一邊拍手一邊繼續動，是不會觸發的。",
      ],
      pros: [
        "裝置端最單純 —— 邊緣不需要任何 AI",
        "隨時可以修改演算法，不必重新部署到裝置",
        "原始影像會保留下來，之後還能再分析",
        "筆電可以重新檢查它看過的任何畫面",
      ],
      cons: [
        "每秒約 583 KB —— 一台攝影機就足以塞爆便宜的網路",
        "你的臉會離開這個房間，在區域網路上傳輸",
        "網路一斷，那幾秒的資料就永遠消失了",
        "100 台攝影機就是 100 倍的頻寬。這種做法無法擴展",
      ],
    },
  },

  2: {
    en: {
      name: "Mode 2 — send the answer",
      tagline: "The Jetson looks. Only numbers travel.",
      senses: "camera + microphone",
      what: "The Jetson looks at the pictures itself and sends only a small " +
        "summary — about 200 bytes of numbers describing how much moved and how " +
        "loud it was. No image is sent at all.",
      why: "It answers the same question with roughly 1,000× less data, and no " +
        "picture of you ever leaves the device. Same rule, same answer — the " +
        "only change is WHERE it is decided.",
      how: [
        "Exactly the same as Mode 1: clap loudly, then freeze.",
        "The rule is identical — loud sound AND motion stopped.",
        "What changed is WHERE it was decided, not HOW.",
        "Watch the video panel: it is blank. That is the point.",
      ],
      pros: [
        "~200 bytes/s instead of ~583 KB — about 1,000× less",
        "No pixel of you ever leaves the device",
        "Survives a network drop — it buffers and catches up",
        "Scales: 100 cameras is still a trickle of data",
      ],
      cons: [
        "The laptop cannot double-check — it never saw an image",
        "A crude rule: a TV or a pet can fool it",
        "Changing the algorithm means redeploying to the device",
        "It knows something moved. It does not know it was a person",
      ],
    },
    zh: {
      name: "模式 2 — 只送出答案",
      tagline: "由 Jetson 觀看，只有數字被送出。",
      senses: "攝影機 + 麥克風",
      what: "Jetson 自己觀看畫面，只送出一組很小的摘要 —— 大約 200 位元組的數字，" +
        "描述「動了多少」以及「有多大聲」。完全不送出任何影像。",
      why: "它用大約少 1,000 倍的資料量回答同一個問題，而且你的影像從未離開裝置。" +
        "規則一樣、答案一樣 —— 唯一改變的是「在哪裡判斷」。",
      how: [
        "和模式 1 完全一樣：用力拍手，然後靜止不動。",
        "規則完全相同 —— 有巨大聲響「而且」動作停止了。",
        "改變的是「在哪裡判斷」，而不是「怎麼判斷」。",
        "請注意影像面板：它是空白的。這正是重點所在。",
      ],
      pros: [
        "每秒約 200 位元組，而不是 583 KB —— 大約少 1,000 倍",
        "你的影像沒有任何一個像素離開裝置",
        "網路中斷也撐得住 —— 會先暫存，恢復後再補送",
        "可以擴展：100 台攝影機的資料量依然很小",
      ],
      cons: [
        "筆電無法覆核 —— 它從來沒看過任何影像",
        "規則很粗糙：電視畫面或寵物都可能騙過它",
        "要修改演算法，就必須重新部署到裝置上",
        "它只知道「有東西動了」，並不知道那是一個人",
      ],
    },
  },

  3: {
    en: {
      name: "Mode 3 — send what it understood",
      tagline: "The Jetson recognises a person. And a posture.",
      senses: "camera + microphone — but it can work on camera alone",
      what: "The Jetson runs a neural network (MoveNet) that finds 17 joints of " +
        "your body, works out whether you are standing, sitting or lying, and " +
        "applies the fall rule itself. It sends the skeleton and its verdict — " +
        "about 600 bytes. Still no image.",
      why: "Modes 1 and 2 only ever know “something moved, and it was loud”. " +
        "Mode 3 knows “a person was upright, and now they are lying on the " +
        "floor”. That is a different question, and a much better one — a fall " +
        "makes no noise if you faint onto carpet.",
      how: [
        "Stand or walk where the camera can see your WHOLE body.",
        "Lie down on the floor and stay there for 3 seconds.",
        "No sound needed — it can see you are lying down.",
        "Want it faster? Clap as you land: 1 second instead of 3.",
        "Not firing? The camera probably cannot see the floor — press “show camera (setup)”.",
      ],
      pros: [
        "Understands posture, not just “something moved”",
        "Catches a SILENT fall — a faint makes no thump",
        "Still tiny: ~600 bytes/s, ~950× under Mode 1",
        "The skeleton is visible proof the AI ran on the device",
        "A thump makes it fire in 1s instead of 3s",
      ],
      cons: [
        "Needs a real model on the device, and more CPU",
        "A 2D camera cannot see a fall straight toward the lens",
        "Camera placement matters more than anything else",
        "It is a rule on top of AI joints, not a trained fall model",
      ],
    },
    zh: {
      name: "模式 3 — 送出它理解到的內容",
      tagline: "Jetson 認得出「人」，也認得出「姿態」。",
      senses: "攝影機 + 麥克風 —— 但只靠攝影機也能運作",
      what: "Jetson 執行一個神經網路（MoveNet），找出你身上 17 個關節點，" +
        "判斷你是站著、坐著還是躺著，並且自己套用跌倒規則。" +
        "它送出的是骨架和判斷結果 —— 大約 600 位元組。一樣沒有影像。",
      why: "模式 1 和模式 2 永遠只知道「有東西動了，而且很大聲」。" +
        "模式 3 知道的是「這個人原本是直立的，現在躺在地上」。" +
        "這是一個不同、而且好得多的問題 —— 因為昏倒在地毯上，是不會發出任何聲音的。",
      how: [
        "站著或走動，讓攝影機能看到你的「全身」。",
        "躺到地上，並且維持 3 秒。",
        "不需要任何聲音 —— 它看得出你正躺著。",
        "想更快嗎？倒下的瞬間拍一下手：1 秒就會觸發，而不是 3 秒。",
        "沒有反應？多半是攝影機看不到地板 —— 按下「顯示攝影機（校正用）」。",
      ],
      pros: [
        "理解的是「姿態」，而不只是「有東西動了」",
        "抓得到「無聲的跌倒」—— 昏倒並不會發出撞擊聲",
        "資料量依然很小：每秒約 600 位元組，比模式 1 少約 950 倍",
        "骨架就是「AI 真的在裝置上執行」的可見證據",
        "若同時聽到撞擊聲，1 秒就會觸發，而不是 3 秒",
      ],
      cons: [
        "裝置上需要一個真正的模型，也需要更多運算資源",
        "2D 攝影機看不出「正對著鏡頭」方向的跌倒",
        "攝影機的擺放位置比其他任何因素都重要",
        "它是「架在 AI 關節點之上的規則」，而不是訓練出來的跌倒模型",
      ],
    },
  },
};

export const MODE_IDS = [1, 2, 3];
