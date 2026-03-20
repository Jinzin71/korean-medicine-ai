"""
herb_knowledge.py — 한약 약재 기능 사전
=========================================================
방약합편 532개 처방에서 사용되는 주요 약재의 기능·효능·타겟을 정의합니다.
유사 처방 비교 시 약재 가감의 의미를 자동 분석하는 데 활용됩니다.

카테고리 체계:
  보기(補氣) / 보혈(補血) / 보음(補陰) / 보양(補陽)
  해표(解表) / 청열(清熱) / 거풍습(祛風濕) / 화담(化痰)
  이기(理氣) / 활혈(活血) / 이수(利水) / 수삽(收澀)
  안신(安神) / 소식(消食) / 방향화습(芳香化濕) / 사하(瀉下)
  온리(溫裏) / 지혈(止血) / 개규(開竅) / 평간(平肝)
  외용(外用) / 조제(調劑)
"""

# ─────────────────────────────────────────────────────────────────────────────
# 약재 기능 사전: {약재명: {category, functions, targets}}
# ─────────────────────────────────────────────────────────────────────────────

HERB_FUNCTIONS: dict[str, dict] = {
    # ══════════════════ 보기(補氣) ══════════════════
    "인삼": {"category": "보기", "functions": ["대보원기", "보비익폐", "생진지갈", "안신증지"],
             "targets": ["기허", "폐허", "비허", "진액부족"]},
    "황기": {"category": "보기", "functions": ["보기승양", "익위고표", "이수소종", "탁창생기"],
             "targets": ["기허", "표허자한", "기함하탈"]},
    "황기(밀초)": {"category": "보기", "functions": ["보중익기", "승양거함"],
                  "targets": ["기허", "중기하함"]},
    "백출": {"category": "보기", "functions": ["건비익기", "조습이수", "고표지한"],
             "targets": ["비허", "습체", "자한"]},
    "백출(초)": {"category": "보기", "functions": ["건비조습"],
                "targets": ["비허", "습체"]},
    "산약": {"category": "보기", "functions": ["보비양위", "생진익폐", "보신삽정"],
             "targets": ["비허", "폐허", "신허"]},
    "산약(초)": {"category": "보기", "functions": ["건비지사"],
                "targets": ["비허설사"]},
    "감초": {"category": "보기", "functions": ["보비익기", "조화제약", "완급지통", "청열해독"],
             "targets": ["비허", "조화", "경련"]},
    "자감초": {"category": "보기", "functions": ["보비화중", "완급지통"],
              "targets": ["비허", "복통"]},
    "대조": {"category": "보기", "functions": ["보중익기", "양혈안신", "완화약성"],
             "targets": ["비허", "혈허", "조화"]},
    "백편두": {"category": "보기", "functions": ["건비화습", "소서"],
              "targets": ["비허습성", "서습"]},

    # ══════════════════ 보혈(補血) ══════════════════
    "당귀": {"category": "보혈", "functions": ["보혈활혈", "조경지통", "윤장통변"],
             "targets": ["혈허", "혈어", "월경부조", "변비"]},
    "당귀(신)": {"category": "보혈", "functions": ["보혈활혈", "조경"],
                "targets": ["혈허", "월경부조"]},
    "당귀(미)": {"category": "활혈", "functions": ["활혈거어", "통경"],
                "targets": ["혈어", "어혈"]},
    "백작약": {"category": "보혈", "functions": ["양혈유간", "완급지통", "염음수한"],
              "targets": ["혈허", "간혈부족", "복통", "자한"]},
    "백작약(주초)": {"category": "보혈", "functions": ["양혈유간"],
                   "targets": ["혈허", "간혈부족"]},
    "적작약": {"category": "활혈", "functions": ["청열양혈", "산어지통"],
              "targets": ["혈열", "어혈통증"]},
    "숙지황": {"category": "보혈", "functions": ["보혈자음", "익정전수"],
              "targets": ["혈허", "음허", "신정부족"]},
    "생지황": {"category": "청열", "functions": ["청열양혈", "양음생진"],
              "targets": ["혈열", "음허", "진액부족"]},
    "건지황": {"category": "보혈", "functions": ["양혈자음"],
              "targets": ["혈허", "음허"]},
    "아교": {"category": "보혈", "functions": ["보혈지혈", "자음윤폐"],
             "targets": ["혈허", "출혈", "음허"]},
    "용안육": {"category": "보혈", "functions": ["보익심비", "양혈안신"],
              "targets": ["심비양허", "불면"]},
    "하수오": {"category": "보혈", "functions": ["보간신", "익정혈", "오수발"],
              "targets": ["간신부족", "정혈허"]},

    # ══════════════════ 보음(補陰) ══════════════════
    "맥문동": {"category": "보음", "functions": ["양음윤폐", "익위생진", "청심제번"],
              "targets": ["폐음허", "위음허", "심번"]},
    "천문동": {"category": "보음", "functions": ["양음윤조", "청폐생진"],
              "targets": ["폐음허", "조열"]},
    "오미자": {"category": "수삽", "functions": ["염폐자신", "생진수한", "삽정지사"],
              "targets": ["폐허해수", "자한도한", "유정설사"]},
    "구기자": {"category": "보음", "functions": ["자보간신", "명목"],
              "targets": ["간신음허", "시력저하"]},
    "석곡": {"category": "보음", "functions": ["양위생진", "자음청열"],
             "targets": ["위음허", "음허열"]},
    "백합": {"category": "보음", "functions": ["양음윤폐", "청심안신"],
             "targets": ["폐음허", "심신불안"]},

    # ══════════════════ 보양(補陽) ══════════════════
    "부자(포)": {"category": "보양", "functions": ["회양구역", "보화소음", "산한지통"],
                "targets": ["양허", "한증", "망양"]},
    "부자": {"category": "보양", "functions": ["회양구역", "보화소음"],
             "targets": ["양허", "한증"]},
    "육계": {"category": "보양", "functions": ["보원양", "난비위", "산한지통", "온경통맥"],
             "targets": ["신양허", "비위한", "한응기체"]},
    "계지": {"category": "해표", "functions": ["발한해기", "온경통양", "조화영위"],
             "targets": ["풍한표증", "경맥한응"]},
    "계심": {"category": "보양", "functions": ["온리산한", "통혈맥"],
             "targets": ["이한", "혈맥불통"]},
    "계피": {"category": "보양", "functions": ["보원양", "산한지통"],
             "targets": ["양허", "한통"]},
    "녹용": {"category": "보양", "functions": ["보신양", "익정혈", "강근골"],
             "targets": ["신양허", "정혈부족"]},
    "익지인": {"category": "보양", "functions": ["온비지사", "온신축뇨", "납기평천"],
              "targets": ["비한설사", "신허유뇨"]},
    "두충": {"category": "보양", "functions": ["보간신", "강근골", "안태"],
             "targets": ["간신부족", "요슬무력"]},
    "두충(강초)": {"category": "보양", "functions": ["보간신", "강근골"],
                 "targets": ["간신부족"]},
    "토사자": {"category": "보양", "functions": ["보신익정", "양간명목"],
              "targets": ["신허", "간허"]},
    "파고지": {"category": "보양", "functions": ["보신조양", "납기평천", "온비지사"],
              "targets": ["신양허", "오경설사"]},
    "파고지(주초)": {"category": "보양", "functions": ["보신양", "고정"],
                   "targets": ["신양허"]},
    "육종용": {"category": "보양", "functions": ["보신양", "익정혈", "윤장통변"],
              "targets": ["신양허", "정혈부족", "변비"]},
    "산수유": {"category": "수삽", "functions": ["보익간신", "삽정고탈"],
              "targets": ["간신부족", "유정", "유뇨"]},

    # ══════════════════ 해표(解表) ══════════════════
    "마황": {"category": "해표", "functions": ["발한해표", "선폐평천", "이수소종"],
             "targets": ["풍한표실", "해수천식", "수종"]},
    "강활": {"category": "해표", "functions": ["해표산한", "거풍제습", "지통"],
             "targets": ["풍한습", "두통신통"]},
    "독활": {"category": "거풍습", "functions": ["거풍습", "지비통", "해표"],
             "targets": ["풍한습비", "요슬통"]},
    "방풍": {"category": "해표", "functions": ["거풍해표", "승습지통", "지경"],
             "targets": ["풍한", "풍습", "경련"]},
    "형개": {"category": "해표", "functions": ["거풍해표", "투진소창"],
             "targets": ["풍한", "발진", "창양"]},
    "갈근": {"category": "해표", "functions": ["해기퇴열", "생진지갈", "승양지사"],
             "targets": ["풍열", "구갈", "설사"]},
    "시호": {"category": "해표", "functions": ["소산퇴열", "소간해울", "승거양기"],
             "targets": ["소양증", "간울", "기함"]},
    "백지": {"category": "해표", "functions": ["거풍산한", "통규지통", "소종배농"],
             "targets": ["풍한두통", "비연", "양명두통"]},
    "곽향": {"category": "방향화습", "functions": ["방향화탁", "화중지구", "해표산한"],
             "targets": ["습탁중조", "구토", "서습"]},
    "자소엽": {"category": "해표", "functions": ["해표산한", "행기관중", "안태"],
              "targets": ["풍한", "기체", "태동불안"]},
    "박하": {"category": "해표", "functions": ["소산풍열", "청두목", "이인후", "투진"],
             "targets": ["풍열", "두통", "인후종통"]},
    "세신": {"category": "해표", "functions": ["거풍산한", "통규지통", "온폐화음"],
             "targets": ["풍한두통", "비색", "한음"]},
    "고본": {"category": "해표", "functions": ["거풍산한", "승습지통"],
             "targets": ["풍한", "전두통"]},
    "향유": {"category": "해표", "functions": ["발한해표", "화습화중", "이수소종"],
             "targets": ["서습", "수종"]},
    "전호": {"category": "화담", "functions": ["강기화담", "소산풍열"],
             "targets": ["담열", "풍열해수"]},
    "선퇴": {"category": "해표", "functions": ["소산풍열", "투진지양", "명목퇴예"],
             "targets": ["풍열", "마진", "목예"]},

    # ══════════════════ 청열(清熱) ══════════════════
    "황금": {"category": "청열", "functions": ["청열조습", "사화해독", "안태"],
             "targets": ["습열", "폐열", "태동"]},
    "황금(주초)": {"category": "청열", "functions": ["청열조습"],
                 "targets": ["습열"]},
    "황련": {"category": "청열", "functions": ["청열조습", "사화해독"],
             "targets": ["습열", "심화", "위화"]},
    "황련(주초)": {"category": "청열", "functions": ["청상초열"],
                 "targets": ["상초습열"]},
    "황련(강초)": {"category": "청열", "functions": ["청위열"],
                 "targets": ["위열"]},
    "황백": {"category": "청열", "functions": ["청열조습", "사화해독", "퇴허열"],
             "targets": ["하초습열", "음허화왕"]},
    "황백(주초)": {"category": "청열", "functions": ["청열조습"],
                 "targets": ["습열"]},
    "치자": {"category": "청열", "functions": ["사화제번", "청열이습", "양혈지혈"],
             "targets": ["심번", "습열황달", "혈열출혈"]},
    "치자(초)": {"category": "청열", "functions": ["양혈지혈"],
                "targets": ["혈열출혈"]},
    "석고": {"category": "청열", "functions": ["청열사화", "제번지갈"],
             "targets": ["기분실열", "위화"]},
    "지모": {"category": "청열", "functions": ["청열사화", "자음윤조"],
             "targets": ["실열", "음허조열"]},
    "지골피": {"category": "청열", "functions": ["양음퇴증열", "청폐강화"],
              "targets": ["음허발열", "폐열"]},
    "연교": {"category": "청열", "functions": ["청열해독", "소옹산결"],
             "targets": ["온열", "창양"]},
    "금은화": {"category": "청열", "functions": ["청열해독", "소산풍열"],
              "targets": ["온열", "옹저창양"]},
    "서각": {"category": "청열", "functions": ["청영양혈", "해독정경"],
             "targets": ["혈열", "경련"]},
    "영양각": {"category": "평간", "functions": ["평간식풍", "청열해독"],
              "targets": ["간풍", "경련"]},
    "현삼": {"category": "청열", "functions": ["양음청열", "해독산결"],
             "targets": ["음허", "인후종통"]},

    # ══════════════════ 이기(理氣) ══════════════════
    "진피": {"category": "이기", "functions": ["이기건비", "조습화담"],
             "targets": ["비위기체", "습담"]},
    "청피": {"category": "이기", "functions": ["소간파기", "소적화체"],
             "targets": ["간기울결", "식적"]},
    "향부자": {"category": "이기", "functions": ["소간이기", "조경지통"],
              "targets": ["간울기체", "월경불조"]},
    "향부자(초)": {"category": "이기", "functions": ["소간이기"],
                 "targets": ["간울기체"]},
    "목향": {"category": "이기", "functions": ["행기지통", "건비소식"],
             "targets": ["기체복통", "비위기체"]},
    "지각": {"category": "이기", "functions": ["이기관중", "행체소비"],
             "targets": ["기체", "완비"]},
    "지실": {"category": "이기", "functions": ["파기소적", "화담제비"],
             "targets": ["기체식적", "담비"]},
    "지실(밀기울초)": {"category": "이기", "functions": ["파기소적"],
                     "targets": ["기체식적"]},
    "오약": {"category": "이기", "functions": ["행기지통", "산한온신"],
             "targets": ["기체한응", "한산복통"]},
    "사인": {"category": "이기", "functions": ["화습행기", "온중지사", "안태"],
             "targets": ["습조기체", "비위한습"]},
    "침향": {"category": "이기", "functions": ["행기지통", "온중강역", "납기평천"],
             "targets": ["기체", "위한구토", "신허천식"]},
    "대복피": {"category": "이기", "functions": ["하기관중", "행수소종"],
              "targets": ["기체", "수종"]},

    # ══════════════════ 활혈(活血) ══════════════════
    "천궁": {"category": "활혈", "functions": ["활혈행기", "거풍지통"],
             "targets": ["혈어", "두통", "풍습비통"]},
    "홍화": {"category": "활혈", "functions": ["활혈통경", "산어지통"],
             "targets": ["혈어", "어혈경폐"]},
    "도인": {"category": "활혈", "functions": ["활혈거어", "윤장통변"],
             "targets": ["혈어", "변비"]},
    "유향": {"category": "활혈", "functions": ["활혈지통", "소종생기"],
             "targets": ["어혈통증", "창양"]},
    "몰약": {"category": "활혈", "functions": ["활혈지통", "소종생기"],
             "targets": ["어혈통증", "창양"]},
    "오령지": {"category": "활혈", "functions": ["활혈산어", "지통"],
              "targets": ["어혈통증"]},
    "삼릉": {"category": "활혈", "functions": ["파혈행기", "소적지통"],
             "targets": ["혈어적취", "식적"]},
    "봉출": {"category": "활혈", "functions": ["행기파혈", "소적지통"],
             "targets": ["기체혈어", "식적"]},
    "현호색": {"category": "활혈", "functions": ["활혈행기", "지통"],
              "targets": ["혈어기체", "제통"]},
    "우슬": {"category": "활혈", "functions": ["활혈거어", "보간신", "강근골", "이수통림"],
             "targets": ["혈어", "간신허", "요슬통"]},
    "소목": {"category": "활혈", "functions": ["활혈거어", "소종지통"],
             "targets": ["혈어", "외상"]},

    # ══════════════════ 화담(化痰) ══════════════════
    "반하": {"category": "화담", "functions": ["조습화담", "강역지구", "소비산결"],
             "targets": ["습담", "구역", "비결"]},
    "반하(제)": {"category": "화담", "functions": ["화담지구"],
                "targets": ["습담", "구역"]},
    "천남성(포)": {"category": "화담", "functions": ["조습화담", "거풍지경", "산결소종"],
                  "targets": ["습담", "중풍", "경련"]},
    "천남성": {"category": "화담", "functions": ["조습화담", "거풍지경"],
              "targets": ["습담", "풍담"]},
    "패모": {"category": "화담", "functions": ["청열화담", "산결소옹"],
             "targets": ["열담", "나력"]},
    "길경": {"category": "화담", "functions": ["선폐거담", "이인후", "배농"],
             "targets": ["해수담다", "인후종통"]},
    "행인": {"category": "화담", "functions": ["지해평천", "윤장통변"],
             "targets": ["해수천식", "변비"]},
    "죽여": {"category": "화담", "functions": ["청열화담", "제번지구"],
             "targets": ["열담", "번구"]},
    "소자": {"category": "화담", "functions": ["강기화담", "지해평천"],
             "targets": ["담옹기역", "해수천식"]},
    "상백피": {"category": "화담", "functions": ["사폐평천", "이수소종"],
              "targets": ["폐열해수", "수종"]},
    "자완": {"category": "화담", "functions": ["윤폐하기", "지해화담"],
             "targets": ["해수담다"]},
    "관동화": {"category": "화담", "functions": ["윤폐하기", "지해화담"],
              "targets": ["해수"]},
    "백개자": {"category": "화담", "functions": ["온폐화담", "이기산결"],
              "targets": ["한담", "담음"]},

    # ══════════════════ 이수(利水) ══════════════════
    "복령": {"category": "이수", "functions": ["이수삼습", "건비화담", "영심안신"],
             "targets": ["수습정체", "비허", "심계불면"]},
    "적복령": {"category": "이수", "functions": ["이수삼습", "통리습열"],
              "targets": ["수습", "습열"]},
    "복신": {"category": "안신", "functions": ["영심안신", "이수"],
             "targets": ["심신불안", "불면"]},
    "택사": {"category": "이수", "functions": ["이수삼습", "설열"],
             "targets": ["수습정체", "습열"]},
    "저령": {"category": "이수", "functions": ["이수삼습"],
             "targets": ["수습정체"]},
    "차전자": {"category": "이수", "functions": ["이수통림", "삼습지사", "명목"],
              "targets": ["수종", "임증"]},
    "목통": {"category": "이수", "functions": ["이수통림", "통경하유"],
             "targets": ["임증", "유즙불통"]},
    "의이인": {"category": "이수", "functions": ["이수삼습", "건비지사", "제비"],
              "targets": ["수습", "비허설사", "비증"]},
    "활석": {"category": "이수", "functions": ["이수통림", "청열해서"],
             "targets": ["습열림증", "서열"]},
    "방기": {"category": "이수", "functions": ["이수소종", "거풍지통"],
             "targets": ["수종", "습열비통"]},
    "비해": {"category": "이수", "functions": ["이습거탁", "거풍제비"],
             "targets": ["고림", "풍습비"]},

    # ══════════════════ 거풍습(祛風濕) ══════════════════
    "위령선": {"category": "거풍습", "functions": ["거풍습", "통경락"],
              "targets": ["풍습비통"]},
    "천마": {"category": "평간", "functions": ["식풍지경", "평간잠양", "거풍통락"],
             "targets": ["간풍내동", "두통현훈", "경련"]},
    "만형자": {"category": "해표", "functions": ["소산풍열", "청리두목"],
              "targets": ["풍열두통", "목적종통"]},
    "진교": {"category": "거풍습", "functions": ["거풍습", "퇴허열", "서근"],
             "targets": ["풍습비통", "음허발열"]},
    "목과": {"category": "거풍습", "functions": ["서근활락", "화습화중"],
             "targets": ["근맥경련", "습비"]},

    # ══════════════════ 온리(溫裏) ══════════════════
    "건강": {"category": "온리", "functions": ["온중산한", "회양통맥", "온폐화음"],
             "targets": ["비위한증", "망양", "한음"]},
    "건강(포)": {"category": "온리", "functions": ["온경지혈", "온중지통"],
                "targets": ["허한출혈", "복통"]},
    "건강(초)": {"category": "온리", "functions": ["온중지사"],
                "targets": ["비한설사"]},
    "생강": {"category": "온리", "functions": ["해표산한", "온중지구", "화담지해"],
             "targets": ["풍한", "위한구토", "해수"]},
    "오수유": {"category": "온리", "functions": ["산한지통", "강역지구", "조습"],
              "targets": ["한응복통", "구역", "습"]},
    "오수유(포)": {"category": "온리", "functions": ["온중지통"],
                 "targets": ["한응복통"]},
    "정향": {"category": "온리", "functions": ["온중강역", "온신조양"],
             "targets": ["위한구토", "신양허"]},
    "회향": {"category": "온리", "functions": ["산한지통", "이기화위"],
             "targets": ["한산복통", "위한"]},
    "초과": {"category": "온리", "functions": ["조습온중", "제담절학"],
             "targets": ["한습", "학질"]},
    "초두구": {"category": "온리", "functions": ["온중거한", "행기조습"],
              "targets": ["한습"]},
    "필발": {"category": "온리", "functions": ["온중산한", "행기지통"],
             "targets": ["위한복통"]},

    # ══════════════════ 사하(瀉下) ══════════════════
    "대황": {"category": "사하", "functions": ["사하공적", "청열사화", "양혈해독", "축어통경"],
             "targets": ["열결변비", "실열", "혈어"]},
    "망초": {"category": "사하", "functions": ["사하통변", "윤조연견", "청화소종"],
             "targets": ["실열변비", "적취"]},
    "마자인": {"category": "사하", "functions": ["윤장통변"],
              "targets": ["장조변비"]},

    # ══════════════════ 안신(安神) ══════════════════
    "산조인(초)": {"category": "안신", "functions": ["양심안신", "염한생진"],
                 "targets": ["심간혈허불면", "도한"]},
    "산조인": {"category": "안신", "functions": ["양심안신"],
              "targets": ["불면"]},
    "원지": {"category": "안신", "functions": ["안신익지", "거담개규", "소옹"],
             "targets": ["심신불안", "건망", "담색"]},
    "주사": {"category": "안신", "functions": ["진심안신", "청열해독"],
             "targets": ["심화항성", "경계불면"]},
    "주사(수비)": {"category": "안신", "functions": ["진심안신"],
                 "targets": ["경계불면"]},
    "백자인": {"category": "안신", "functions": ["양심안신", "윤장통변"],
              "targets": ["심혈부족불면", "변비"]},
    "석창포": {"category": "개규", "functions": ["개규영신", "화습화위"],
              "targets": ["담미심규", "건망"]},
    "연자육": {"category": "수삽", "functions": ["보비지사", "양심안신", "익신고정"],
              "targets": ["비허설사", "불면", "유정"]},

    # ══════════════════ 소식(消食) ══════════════════
    "신곡": {"category": "소식", "functions": ["소식화적", "건비화위"],
             "targets": ["식적", "비위불화"]},
    "신곡(초)": {"category": "소식", "functions": ["건비소식"],
                "targets": ["식적"]},
    "산사": {"category": "소식", "functions": ["소식화적", "행기산어"],
             "targets": ["육식적체", "어혈"]},
    "맥아": {"category": "소식", "functions": ["소식건위", "회유소창"],
             "targets": ["곡식적체"]},
    "맥아(초)": {"category": "소식", "functions": ["건위소식"],
                "targets": ["식적"]},
    "빈랑": {"category": "소식", "functions": ["소적도체", "행기이수", "구충"],
             "targets": ["식적기체", "수종", "충적"]},

    # ══════════════════ 방향화습(芳香化濕) ══════════════════
    "창출": {"category": "방향화습", "functions": ["조습건비", "거풍산한", "명목"],
             "targets": ["습곤비위", "풍습", "야맹"]},
    "후박": {"category": "방향화습", "functions": ["조습소담", "하기제만"],
             "targets": ["습체", "기체복만"]},
    "백두구": {"category": "방향화습", "functions": ["화습행기", "온중지구"],
              "targets": ["습조기체", "위한구토"]},
    "승마": {"category": "해표", "functions": ["발표투진", "청열해독", "승거양기"],
             "targets": ["마진", "열독", "기함하탈"]},

    # ══════════════════ 수삽(收澀) ══════════════════
    "오매": {"category": "수삽", "functions": ["염폐지해", "삽장지사", "안회구충", "생진지갈"],
             "targets": ["폐허해수", "구사", "회충", "소갈"]},

    # ══════════════════ 지혈(止血) ══════════════════
    "포황(초)": {"category": "지혈", "functions": ["지혈화어"],
                "targets": ["출혈"]},
    "지유": {"category": "지혈", "functions": ["양혈지혈", "해독렴창"],
             "targets": ["혈열출혈", "창양"]},
    "애엽": {"category": "지혈", "functions": ["온경지혈", "산한조습"],
             "targets": ["허한출혈"]},

    # ══════════════════ 개규(開竅) ══════════════════
    "사향": {"category": "개규", "functions": ["개규성신", "활혈통경", "지통소옹"],
             "targets": ["신혼", "어혈", "옹저"]},
    "우황": {"category": "개규", "functions": ["개규성신", "청열해독", "식풍지경"],
             "targets": ["열병신혼", "경련"]},
    "용뇌": {"category": "개규", "functions": ["개규성신", "청열지통"],
             "targets": ["신혼", "열통"]},
    "소합향": {"category": "개규", "functions": ["개규벽예", "거담온중"],
              "targets": ["한폐신혼"]},
    "안식향": {"category": "개규", "functions": ["개규벽예", "행기활혈"],
              "targets": ["중풍담궐"]},

    # ══════════════════ 평간(平肝) ══════════════════
    "용골": {"category": "평간", "functions": ["진심안신", "평간잠양", "삽정고탈"],
             "targets": ["심신불안", "간양상항"]},
    "자석": {"category": "평간", "functions": ["진심안신", "잠양납기"],
             "targets": ["심계", "이명"]},

    # ══════════════════ 외용/조제(外用/調劑) ══════════════════
    "총백": {"category": "해표", "functions": ["발한해표", "산한통양"],
             "targets": ["풍한", "양기불통"]},
    "갱미": {"category": "조제", "functions": ["보중익기", "건비양위"],
             "targets": ["비위허"]},
    "등심초": {"category": "이수", "functions": ["청심강화", "이수통림"],
              "targets": ["심화", "임증"]},
    "죽엽": {"category": "청열", "functions": ["청열제번", "생진이뇨"],
             "targets": ["열병번갈"]},
    "죽력": {"category": "화담", "functions": ["청열활담", "진경개규"],
             "targets": ["열담", "중풍"]},
    "봉밀": {"category": "보기", "functions": ["보중윤조", "완급지통"],
             "targets": ["비위허", "변비"]},
    "금박": {"category": "안신", "functions": ["진심안신"],
             "targets": ["경계"]},
    "진사": {"category": "안신", "functions": ["진심안신", "청열해독"],
             "targets": ["경계"]},
    "석웅황": {"category": "외용", "functions": ["해독", "연견소적"],
              "targets": ["옹저", "적취"]},
}

# ─────────────────────────────────────────────────────────────────────────────
# 카테고리 한글 설명
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_DESC = {
    "보기": "기(氣)를 보충하여 기허 상태를 개선",
    "보혈": "혈(血)을 보충하여 혈허 상태를 개선",
    "보음": "음액을 보충하여 음허 상태를 개선",
    "보양": "양기를 보충하여 양허/한증을 개선",
    "해표": "외감(外感) 표증을 풀어 감기·발열 치료",
    "청열": "체내 열독을 식히고 염증을 해소",
    "이기": "기(氣)의 흐름을 원활히 하여 기체·울결 해소",
    "활혈": "혈액순환을 촉진하여 어혈·통증 해소",
    "화담": "담음(痰飲)을 제거하여 해수·담다 치료",
    "이수": "수습(水濕)을 제거하여 부종·소변불리 치료",
    "거풍습": "풍습을 제거하여 관절통·비증 치료",
    "온리": "내부를 따뜻하게 하여 한증·복통 치료",
    "사하": "대변을 통하게 하여 변비·적체 치료",
    "안신": "심신을 안정시켜 불면·경계 치료",
    "소식": "식적(食積)을 소화시켜 소화불량 치료",
    "방향화습": "향기로 습을 제거하여 비위 습곤 치료",
    "수삽": "고삽(固澀)으로 유정·유뇨·설사 치료",
    "지혈": "출혈을 멈추게 함",
    "개규": "의식을 깨우고 신혼(神昏) 치료",
    "평간": "간양을 가라앉히고 경련·현훈 치료",
    "외용": "외부 적용",
    "조제": "약성 조화·보조",
}

# ─────────────────────────────────────────────────────────────────────────────
# 체질 경향 매핑 (카테고리 → 체질 친화도)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_CONSTITUTION = {
    "보기": ["기허체질", "소음인"],
    "보혈": ["혈허체질", "소음인"],
    "보음": ["음허체질", "소양인"],
    "보양": ["양허체질", "소음인"],
    "해표": ["표증", "실증"],
    "청열": ["열증", "소양인", "실열"],
    "이기": ["기울체질", "간울"],
    "활혈": ["어혈체질"],
    "화담": ["담습체질", "태음인"],
    "이수": ["수습체질", "태음인"],
    "온리": ["한증", "소음인", "양허"],
    "사하": ["실증", "열결"],
    "안신": ["심허", "불면"],
    "소식": ["식적"],
    "방향화습": ["습곤", "태음인"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 분석 유틸리티 함수
# ─────────────────────────────────────────────────────────────────────────────

def get_herb_info(herb_name: str) -> dict:
    """약재 기능 정보 반환 (없으면 빈 dict)"""
    return HERB_FUNCTIONS.get(herb_name, {})


def analyze_herb_group(herbs: list[str]) -> dict:
    """
    약재 그룹의 카테고리 분포 분석.

    Returns:
        {
            "categories": {"보기": 3, "활혈": 2, ...},
            "main_categories": ["보기", "활혈"],  # 상위 2개
            "all_targets": ["기허", "혈어", ...],
            "known_count": 15,
            "unknown_count": 3,
            "unknown_herbs": ["약재X", ...]
        }
    """
    from collections import Counter  # noqa: F811
    categories = Counter()
    all_targets = []
    unknown = []

    for h in herbs:
        info = HERB_FUNCTIONS.get(h, {})
        if info:
            categories[info["category"]] += 1
            all_targets.extend(info.get("targets", []))
        else:
            unknown.append(h)

    sorted_cats = categories.most_common()
    main_cats = [c for c, _ in sorted_cats[:2]] if sorted_cats else []

    return {
        "categories": dict(sorted_cats),
        "main_categories": main_cats,
        "all_targets": list(dict.fromkeys(all_targets)),  # 순서 유지 중복 제거
        "known_count": len(herbs) - len(unknown),
        "unknown_count": len(unknown),
        "unknown_herbs": unknown,
    }


def analyze_herb_diff(target_herbs: list[str], other_herbs: list[str]) -> dict:  # noqa: C901
    """
    두 처방의 약재 차이를 기능적으로 분석.

    Returns:
        {
            "added": [{"herb": "천궁", "category": "활혈", "functions": [...], "meaning": "..."}],
            "removed": [{"herb": "인삼", ...}],
            "direction_change": "보기 위주 → 활혈 강화",
            "target_shift": "기허 치료 → 어혈 해소 추가",
        }
    """
    added_herbs = sorted(set(other_herbs) - set(target_herbs))
    removed_herbs = sorted(set(target_herbs) - set(other_herbs))

    added_info = []
    for h in added_herbs:
        info = HERB_FUNCTIONS.get(h, {})
        added_info.append({
            "herb": h,
            "category": info.get("category", "미등록"),
            "functions": info.get("functions", []),
            "targets": info.get("targets", []),
        })

    removed_info = []
    for h in removed_herbs:
        info = HERB_FUNCTIONS.get(h, {})
        removed_info.append({
            "herb": h,
            "category": info.get("category", "미등록"),
            "functions": info.get("functions", []),
            "targets": info.get("targets", []),
        })

    # 방향 변화 분석
    from collections import Counter
    added_cats = Counter(i["category"] for i in added_info if i["category"] != "미등록")
    removed_cats = Counter(i["category"] for i in removed_info if i["category"] != "미등록")

    direction_parts = []
    for cat in set(list(added_cats.keys()) + list(removed_cats.keys())):
        a = added_cats.get(cat, 0)
        r = removed_cats.get(cat, 0)
        desc = CATEGORY_DESC.get(cat, cat)
        if a > r:
            direction_parts.append(f"{cat}({desc}) 강화 (+{a-r})")
        elif r > a:
            direction_parts.append(f"{cat}({desc}) 약화 (-{r-a})")

    # 타겟 변화
    added_targets = set()
    for i in added_info:
        added_targets.update(i["targets"])
    removed_targets = set()
    for i in removed_info:
        removed_targets.update(i["targets"])
    new_targets = added_targets - removed_targets
    lost_targets = removed_targets - added_targets

    target_shift_parts = []
    if new_targets:
        target_shift_parts.append(f"추가 타겟: {', '.join(sorted(new_targets))}")
    if lost_targets:
        target_shift_parts.append(f"감소 타겟: {', '.join(sorted(lost_targets))}")

    return {
        "added": added_info,
        "removed": removed_info,
        "direction_change": " / ".join(direction_parts) if direction_parts else "유사한 치료 방향",
        "target_shift": " / ".join(target_shift_parts) if target_shift_parts else "타겟 질병군 유사",
    }


def format_herb_diff_analysis(target_name: str, other_name: str,
                               target_herbs: list[str], other_herbs: list[str],
                               target_indications: list[str] = None,
                               other_indications: list[str] = None) -> str:
    """
    두 처방의 약재 차이를 마크다운으로 포맷팅.
    """
    diff = analyze_herb_diff(target_herbs, other_herbs)
    sections = []

    sections.append(f"**📋 {target_name} vs {other_name} — 차이 분석**\n")

    # 추가 약재 분석
    if diff["added"]:
        sections.append("**추가된 약재의 기능:**")
        for item in diff["added"]:
            if item["functions"]:
                func_str = ", ".join(item["functions"][:3])
                sections.append(f"- **{item['herb']}** ({item['category']}): {func_str}")
            else:
                sections.append(f"- **{item['herb']}** (기능정보 미등록)")

    # 제거 약재 분석
    if diff["removed"]:
        sections.append("\n**제거된 약재의 기능:**")
        for item in diff["removed"]:
            if item["functions"]:
                func_str = ", ".join(item["functions"][:3])
                sections.append(f"- ~~{item['herb']}~~ ({item['category']}): {func_str}")
            else:
                sections.append(f"- ~~{item['herb']}~~ (기능정보 미등록)")

    # 치료 방향 변화
    sections.append(f"\n**치료 방향 변화:** {diff['direction_change']}")
    sections.append(f"**타겟 변화:** {diff['target_shift']}")

    # 적응증 비교
    if target_indications and other_indications:
        shared = sorted(set(target_indications) & set(other_indications))
        only_target = sorted(set(target_indications) - set(other_indications))
        only_other = sorted(set(other_indications) - set(target_indications))
        if shared:
            sections.append(f"\n**공통 적응증:** {', '.join(shared[:8])}")
        if only_target:
            sections.append(f"**{target_name}만:** {', '.join(only_target[:8])}")
        if only_other:
            sections.append(f"**{other_name}만:** {', '.join(only_other[:8])}")

    # 체질 경향
    target_group = analyze_herb_group(target_herbs)
    other_group = analyze_herb_group(other_herbs)
    target_const = set()
    for cat in target_group["main_categories"]:
        target_const.update(CATEGORY_CONSTITUTION.get(cat, []))
    other_const = set()
    for cat in other_group["main_categories"]:
        other_const.update(CATEGORY_CONSTITUTION.get(cat, []))

    if target_const or other_const:
        sections.append(f"\n**체질 경향:**")
        if target_const:
            sections.append(f"- {target_name}: {', '.join(sorted(target_const))}")
        if other_const:
            sections.append(f"- {other_name}: {', '.join(sorted(other_const))}")

    return "\n".join(sections)
