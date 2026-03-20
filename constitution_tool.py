"""
constitution_tool.py — 한의학 체질 객관화 평가 도구
=========================================================
5개 레이어로 구성된 다층 체질 평가 시스템.
BMI처럼 수치로 표현 가능한 지표들을 조합합니다.

[레이어 구성]
  L1. 체형 계측 지표   — 완전 객관 (신장·체중·둘레 측정값)
  L2. 한열허실 지수    — 반객관 (체온 + 자각증상 VAS)
  L3. 기혈음양 프로파일 — 16문항 자가평가 설문
  L4. 소화·배변·수면 기능 지수 — 표준화 척도 기반
  L5. 사상체질 스크리닝 — 간소화 QSCC 기반 15문항

[출력]
  - 사상체질 스크리닝 점수 (태양/태음/소양/소음 %)
  - 한열 지수 HCI (Cold-Heat Index, -5 ~ +5)
  - 허실 지수 DEI (Deficiency-Excess Index, -5 ~ +5)
  - 기혈음양 프로파일 벡터 (4점수)
  - 체형 지수 (BMI + 상하체균형 + 복부지수)
  - 처방 적합성 매핑 (위 지표를 처방 선택 기준으로 변환)

[향후 확장 가능 지표 — 객관화 보조 도구]
  L6. 설진(舌診) 디지털화
      - 설색(舌色): 담백/홍/강홍 → 한열 보정
      - 설태(苔): 백/황/지니 → 한열+허실 보정
      - 설형(舌形): 치흔/비대 → 기허·수독 보정
      → 향후 이미지 인식 모델 연동 예정

  L7. 맥진(脈診) 객관화
      - 맥파분석기(Pulse Wave Analyzer) 데이터
      - 맥압(pulse pressure), 맥파전달속도(PWV)
      - AI(Augmentation Index) → 혈관 탄성도
      → 한열·허실 보조 지표로 활용

  L8. HRV (Heart Rate Variability)
      - LF/HF ratio → 교감/부교감 균형
      - RMSSD → 부교감 활성도
      → 한열(교감우세=열, 부교감우세=한) 보정
      → 스트레스 지수 → 기울(氣鬱) 평가

  L9. 체온분포 (Thermography)
      - 상하체 체온편차 (상열하한 패턴 감지)
      - 좌우 체온 비대칭 (경락 불균형)
      → HCI 한열 지수 보정에 직접 활용

  L10. InBody 체성분 분석
      - 세포내수분/세포외수분 비율 → 수독(水毒) 평가
      - 근육량/체지방량 분포 → 상하체 균형
      - 부종지수 → 양허 보조 평가
      → BMI 단독보다 정밀한 체형 분류

  L11. 혈액검사 연동
      - CBC (빈혈 지표): Hb, Fe, Ferritin → 혈허 객관화
      - TSH, fT4 → 양허(갑상선 기능저하) 보조
      - ESR, CRP → 실증/열증 보조
      - AST/ALT → 간열(肝熱) 참고
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ─────────────────────────────────────────────────────────────────────────────
# 데이터 모델
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AnthropometricData:
    """L1: 체형 계측 지표 (직접 측정값)"""
    height_cm: float          # 신장 (cm)
    weight_kg: float          # 체중 (kg)
    waist_cm: float           # 복위 (배꼽 높이)
    hip_cm: float             # 골반위
    chest_cm: float           # 흉위 (유두 높이)
    neck_cm: float            # 경위
    shoulder_cm: float        # 어깨너비 (옆 견봉 기준)
    age: int
    sex: str                  # "M" / "F"


@dataclass
class ThermalFunctionData:
    """L2: 한열허실 입력"""
    basal_temp: float         # 기초체온 (°C, 측정값)
    cold_heat_pref: int       # 냉온 선호 (-5 한 ~ +5 열, 자가평가)
    thirst_level: int         # 갈증 정도 (0~10)
    daily_water_ml: int       # 하루 음수량 (ml)
    sweat_level: int          # 발한량 (0~4: 없음~매우많음)
    heat_intolerance: bool    # 더위를 심하게 탐
    cold_intolerance: bool    # 추위를 심하게 탐


@dataclass
class QiBloodYinYangData:
    """L3: 기혈음양 16문항 설문 (각 항목 0~10 VAS)"""
    # 기허(氣虛) 4문항
    fatigue_resting: int       # 쉬어도 피로가 풀리지 않는다
    exertional_dyspnea: int    # 조금만 움직여도 숨이 차다
    postmeal_fatigue: int      # 식후 심하게 졸리고 처진다
    voice_low: int             # 목소리가 작고 힘이 없다

    # 혈허(血虛) 4문항
    dizziness_standing: int    # 일어날 때 어지럽다
    pale_complexion: int       # 안색이 창백하고 윤기가 없다
    menstrual_sparse: int      # 생리량이 적거나 주기가 불규칙 (남성=0)
    numbness_limbs: int        # 손발이 저리거나 감각이 무디다

    # 음허(陰虛) 4문항
    afternoon_heat: int        # 오후~저녁에 열감이 있다
    night_sweat: int           # 자다가 식은땀을 흘린다
    dry_mouth_throat: int      # 입·목이 건조하다 (저녁에 심함)
    tinnitus_dizziness: int    # 이명, 어지러움이 있다

    # 양허(陽虛) 4문항
    cold_limbs: int            # 손발·배가 차다
    nocturia: int              # 야간 소변 횟수가 많다 (1회=3, 2회=6, 3+회=10)
    edema_morning: int         # 아침에 얼굴·발이 붓는다
    low_back_cold_pain: int    # 허리가 시리고 아프다


@dataclass
class DigestiveFunctionData:
    """L4: 소화·배변·수면 기능 지수"""
    appetite_vas: int          # 식욕 VAS (0~10)
    digestion_vas: int         # 소화력 자가평가 (0=최악, 10=최상)
    stool_consistency: int     # 대변 굳기 (Bristol 1~7)
    stool_frequency: int       # 하루 배변 횟수
    sleep_quality: int         # 수면의 질 (0~10, 높을수록 좋음)
    sleep_hours: float         # 수면 시간
    bowel_bloating: int        # 식후 복부 팽만 (0~10)


@dataclass
class SasangScreeningData:
    """
    L5: 사상체질 스크리닝 — QSCC 간소화 15문항
    각 문항: 0(전혀아님) ~ 3(매우그렇다)

    [체형·생리]
    q1: 상체(목·어깨)가 하체(엉덩이·허벅지)보다 더 발달했다
    q2: 살이 잘 찌고 체격이 큰 편이다
    q3: 땀을 쉽게 많이 흘린다 (움직임에 비해)
    q4: 소화가 잘 안 되고 자주 체한다

    [성격·기질]
    q5: 외향적이고 사교적이며 즉흥적이다
    q6: 꼼꼼하고 신중하며 내향적이다
    q7: 리더십이 강하고 결단력이 있다
    q8: 불안이나 걱정이 많고 안정을 추구한다

    [건강 패턴]
    q9: 감기에 잘 걸리고 기침·콧물이 잘 낫지 않는다
    q10: 열이 잘 나고 상기되는 경향이 있다
    q11: 소변이 시원하게 나오지 않는다
    q12: 변비 경향이 있다

    [체력·활동]
    q13: 평소 체력이 강하고 많이 움직인다
    q14: 쉽게 피로하고 오래 서있기 힘들다
    q15: 상체에 힘이 없고 하체(다리)가 불안정하다
    """
    q1: int; q2: int; q3: int; q4: int; q5: int
    q6: int; q7: int; q8: int; q9: int; q10: int
    q11: int; q12: int; q13: int; q14: int; q15: int


@dataclass
class ConstitutionProfile:
    """최종 체질 평가 결과"""
    # 사상체질 점수 (합계 100)
    taeyang_pct: float         # 태양인 (太陽人)
    taeeum_pct: float          # 태음인 (太陰人)
    soyang_pct: float          # 소양인 (少陽人)
    soeum_pct: float           # 소음인 (少陰人)
    dominant_type: str         # 최고점 체질

    # 한열 지수 HCI (-5 한 ~ +5 열)
    hci: float

    # 허실 지수 DEI (-5 허 ~ +5 실)
    dei: float

    # 기혈음양 프로파일 (각 0~10)
    qi_deficiency: float       # 기허 지수
    blood_deficiency: float    # 혈허 지수
    yin_deficiency: float      # 음허 지수
    yang_deficiency: float     # 양허 지수

    # 체형 지표
    bmi: float
    whr: float                 # Waist-Hip Ratio
    cwr: float                 # Chest-Waist Ratio (흉위/복위)
    shoulder_hip_ratio: float  # 어깨/골반 비율

    # 처방 적합성 태그
    prescription_tags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# 평가 엔진
# ─────────────────────────────────────────────────────────────────────────────

class ConstitutionAssessor:
    """
    5개 레이어 입력을 받아 ConstitutionProfile을 계산합니다.

    사용 예시:
        assessor = ConstitutionAssessor()
        profile = assessor.assess(anthro, thermal, qi_blood, digestive, sasang)
        print(profile.dominant_type, profile.hci, profile.dei)
    """

    # ── L1: 체형 계측 지표 계산 ───────────────────────────────────────────────

    def calc_anthropometrics(self, a: AnthropometricData) -> dict:
        """BMI, WHR, 흉복비, 어깨골반비 계산"""
        bmi = a.weight_kg / (a.height_cm / 100) ** 2
        whr = a.waist_cm / a.hip_cm if a.hip_cm > 0 else 0
        cwr = a.chest_cm / a.waist_cm if a.waist_cm > 0 else 0  # 클수록 상체 발달
        shr = a.shoulder_cm / a.hip_cm if a.hip_cm > 0 else 0

        return {
            "bmi": round(bmi, 1),
            "whr": round(whr, 2),
            "cwr": round(cwr, 2),
            "shr": round(shr, 2),
            # 비만 분류 (아시아 기준)
            "bmi_class": (
                "저체중" if bmi < 18.5 else
                "정상" if bmi < 23 else
                "과체중" if bmi < 25 else
                "비만1단계" if bmi < 30 else "비만2단계"
            ),
        }

    # ── L2: 한열 지수 (HCI) ───────────────────────────────────────────────────

    def calc_hci(self, t: ThermalFunctionData) -> float:
        """
        Cold-Heat Index (한열 지수): -5 (寒) ~ +5 (熱)
        체온, 냉온 선호, 갈증, 발한을 종합.
        """
        score = 0.0

        # 기초체온 기여 (정상 36.5 기준)
        temp_delta = t.basal_temp - 36.5
        score += temp_delta * 2.0  # ±1°C → ±2점

        # 냉온 선호 (-5~+5 입력을 그대로 반영, 가중치 0.4)
        score += t.cold_heat_pref * 0.4

        # 갈증 (열증 지표: 0~10, 기여 최대 +1)
        score += (t.thirst_level - 5) * 0.1

        # 발한 (열증 지표 but 양허에서도 자한: 구분 필요)
        if t.heat_intolerance:
            score += 1.0
        if t.cold_intolerance:
            score -= 1.0

        # 음수량 (하루 2L 기준: 많으면 열, 적으면 한)
        water_delta = (t.daily_water_ml - 2000) / 1000
        score += water_delta * 0.5

        return round(max(-5, min(5, score)), 1)

    # ── L3: 기혈음양 프로파일 ─────────────────────────────────────────────────

    def calc_qi_blood_profile(self, q: QiBloodYinYangData) -> dict:
        """각 허증 지수 0~10 계산"""
        qi_def = (q.fatigue_resting + q.exertional_dyspnea +
                  q.postmeal_fatigue + q.voice_low) / 4
        blood_def = (q.dizziness_standing + q.pale_complexion +
                     q.menstrual_sparse + q.numbness_limbs) / 4
        yin_def = (q.afternoon_heat + q.night_sweat +
                   q.dry_mouth_throat + q.tinnitus_dizziness) / 4
        yang_def = (q.cold_limbs + q.nocturia +
                    q.edema_morning + q.low_back_cold_pain) / 4
        return {
            "qi": round(qi_def, 1),
            "blood": round(blood_def, 1),
            "yin": round(yin_def, 1),
            "yang": round(yang_def, 1),
        }

    # ── L2+L3: 허실 지수 (DEI) ────────────────────────────────────────────────

    def calc_dei(self, thermal: ThermalFunctionData,
                 qi_blood: QiBloodYinYangData,
                 digestive: DigestiveFunctionData) -> float:
        """
        Deficiency-Excess Index: -5 (虛) ~ +5 (實)
        허증(虛證)이 강할수록 음수, 실증(實證)이 강할수록 양수.
        """
        qb = self.calc_qi_blood_profile(qi_blood)
        # 기혈음양허 평균 → 허증 정도
        deficiency_mean = (qb["qi"] + qb["blood"] + qb["yin"] + qb["yang"]) / 4
        # 소화·체력 지수 → 실증 기여
        vitality = (digestive.appetite_vas + digestive.digestion_vas) / 2
        # 발한·체력 (허할수록 자한 경향)
        sweat_penalty = thermal.sweat_level * 0.2 if thermal.sweat_level > 2 else 0

        # DEI = 활력 - 허증 - 발한패널티, 중심값 0
        dei = (vitality - deficiency_mean - sweat_penalty) / 2
        return round(max(-5, min(5, dei)), 1)

    # ── L5: 사상체질 스크리닝 ─────────────────────────────────────────────────

    def calc_sasang_scores(self,
                           s: SasangScreeningData,
                           anthro: AnthropometricData,
                           a_vals: dict) -> dict:
        """
        사상체질 4개 스크리닝 점수 계산.

        핵심 문헌 근거:
        - 태양인: 목·상체 강건, 하체 약함, 목덜미 발달, 상체>하체
        - 태음인: 체격 크고 살찜, 땀 많음, 소화 약함, 변비 경향
        - 소양인: 외향·민첩, 상열 경향, 소변 불편, 상체>하체 but 골반 발달
        - 소음인: 내향·신중, 소화 예민, 피로, 추위를 탐, 마른 체형

        QSCC-II 연구: 소음인↔소양인 변별력 최고, 태음인 구별 어려움
        → 태음인은 체형 지수에 높은 가중치 부여
        """
        scores = {"taeyang": 0.0, "taeeum": 0.0, "soyang": 0.0, "soeum": 0.0}

        # ── 설문 기반 점수 ────────────────────────────────────────────
        # 태양인: q1(상체>하체), q7(결단력), q15(하체불안정)
        scores["taeyang"] += s.q1 * 2.0 + s.q7 * 1.5 + s.q15 * 2.0

        # 태음인: q2(살찜), q3(땀), q4(소화약), q12(변비), q13(체력강)
        scores["taeeum"] += (s.q2 * 2.0 + s.q3 * 1.5 + s.q4 * 1.0 +
                             s.q12 * 1.0 + s.q13 * 1.0)

        # 소양인: q5(외향), q7(리더십), q10(상열), q11(소변불편)
        scores["soyang"] += (s.q5 * 2.0 + s.q7 * 1.0 + s.q10 * 2.0 +
                             s.q11 * 1.5)

        # 소음인: q6(내향), q8(불안), q4(소화약), q9(감기), q14(피로), q15(불안정)
        scores["soeum"] += (s.q6 * 2.0 + s.q8 * 1.5 + s.q4 * 1.0 +
                            s.q9 * 1.0 + s.q14 * 1.5)

        # ── 체형 지수 기반 보정 ───────────────────────────────────────
        bmi = a_vals["bmi"]
        cwr = a_vals["cwr"]  # 흉위/복위 (>1: 상체 발달)
        shr = a_vals["shr"]  # 어깨/골반 비율

        # 태음인: BMI 높음, 땀 많음 → 보정
        if bmi >= 25:
            scores["taeeum"] += (bmi - 25) * 0.5
        if bmi >= 28:
            scores["taeeum"] += 3.0

        # 태양인: 상체 강건, 하체 약함 → 높은 shr
        if shr > 1.0:
            scores["taeyang"] += (shr - 1.0) * 5.0

        # 소음인: 마른 체형 → BMI 낮음
        if bmi < 20:
            scores["soeum"] += (20 - bmi) * 0.3
        if bmi < 18.5:
            scores["soeum"] += 3.0

        # 소양인: 하체(골반) 발달, 상체는 상대적으로 좁음
        if shr < 0.92:
            scores["soyang"] += (0.92 - shr) * 5.0

        # 흉복비: 높을수록 상체 > 하체 (태양인/일부 태음인)
        if cwr > 1.05:
            scores["taeyang"] += (cwr - 1.05) * 3.0

        # ── 정규화 (softmax 유사) ─────────────────────────────────────
        total = sum(scores.values())
        if total == 0:
            total = 1
        normalized = {k: round(v / total * 100, 1) for k, v in scores.items()}
        dominant = max(normalized, key=normalized.get)

        name_map = {
            "taeyang": "태양인(太陽人)",
            "taeeum": "태음인(太陰人)",
            "soyang": "소양인(少陽人)",
            "soeum": "소음인(少陰人)",
        }
        return {**normalized, "dominant": name_map[dominant], "dominant_key": dominant}

    # ── 처방 태그 매핑 ─────────────────────────────────────────────────────────

    def map_prescription_tags(self, profile_data: dict) -> tuple[list[str], list[str]]:
        """
        체질 프로파일을 처방 선택 태그로 변환.
        Returns: (tags, notes)
        """
        tags = []
        notes = []
        hci = profile_data["hci"]
        dei = profile_data["dei"]
        qi = profile_data["qi_blood"]["qi"]
        blood = profile_data["qi_blood"]["blood"]
        yin = profile_data["qi_blood"]["yin"]
        yang = profile_data["qi_blood"]["yang"]
        dominant_key = profile_data["sasang"]["dominant_key"]
        bmi = profile_data["anthro"]["bmi"]

        # 한열 태그
        if hci <= -2:
            tags.append("寒證(한증)")
            notes.append("따뜻한 성질의 처방 선호 — 온리산한(溫裏散寒) 약재 포함 처방")
        elif hci >= 2:
            tags.append("熱證(열증)")
            notes.append("청열(淸熱) 성질 처방 선호 — 황련·황금·치자 등 포함")
        else:
            tags.append("平(평)")

        # 허실 태그
        if dei <= -2:
            tags.append("虛證(허증)")
            notes.append("보익(補益) 처방 적합 — 보기·보혈·보음·보양 방향 결정 필요")
        elif dei >= 2:
            tags.append("實證(실증)")
            notes.append("공하·사하 처방 가능 — 대황·망초 등 포함 처방 고려")

        # 기혈음양 태그 (7점 이상: 강한 허증)
        if qi >= 7:
            tags.append("氣虛(기허)")
            notes.append("인삼·황기 포함 보기제 — 보중익기탕·사군자탕 계열")
        if blood >= 7:
            tags.append("血虛(혈허)")
            notes.append("숙지황·당귀 포함 보혈제 — 사물탕·쌍화탕 계열")
        if yin >= 7:
            tags.append("陰虛(음허)")
            notes.append("음허: 육미지황탕·자음강화탕 계열")
        if yang >= 7:
            tags.append("陽虛(양허)")
            notes.append("양허: 팔미지황탕·우귀환 계열")

        # 사상체질 태그
        sasang_tags = {
            "taeyang": ("太陽人체질", "태양인용 처방: 오가피장척탕·미후도식장탕"),
            "taeeum": ("太陰人체질", "태음인용 처방: 태음조위탕·청폐사간탕"),
            "soyang": ("少陽人체질", "소양인용 처방: 형방지황탕·독활지황탕"),
            "soeum": ("少陰人체질", "소음인용 처방: 향사양위탕·팔물군자탕"),
        }
        tag, note = sasang_tags.get(dominant_key, ("", ""))
        if tag:
            tags.append(tag)
            notes.append(note)

        # BMI 태그
        if bmi >= 25:
            tags.append("過體重(과체중)")
        if bmi < 18.5:
            tags.append("低體重(저체중)")

        return tags, notes

    # ── 통합 평가 ─────────────────────────────────────────────────────────────

    def assess(
        self,
        anthro: AnthropometricData,
        thermal: ThermalFunctionData,
        qi_blood: QiBloodYinYangData,
        digestive: DigestiveFunctionData,
        sasang: SasangScreeningData,
    ) -> ConstitutionProfile:
        """5개 레이어 입력 → ConstitutionProfile 반환"""
        a_vals = self.calc_anthropometrics(anthro)
        qb_vals = self.calc_qi_blood_profile(qi_blood)
        hci = self.calc_hci(thermal)
        dei = self.calc_dei(thermal, qi_blood, digestive)
        s_scores = self.calc_sasang_scores(sasang, anthro, a_vals)

        combined = {
            "hci": hci, "dei": dei,
            "qi_blood": qb_vals,
            "anthro": a_vals,
            "sasang": s_scores,
        }
        tags, notes = self.map_prescription_tags(combined)

        return ConstitutionProfile(
            taeyang_pct=s_scores["taeyang"],
            taeeum_pct=s_scores["taeeum"],
            soyang_pct=s_scores["soyang"],
            soeum_pct=s_scores["soeum"],
            dominant_type=s_scores["dominant"],
            hci=hci,
            dei=dei,
            qi_deficiency=qb_vals["qi"],
            blood_deficiency=qb_vals["blood"],
            yin_deficiency=qb_vals["yin"],
            yang_deficiency=qb_vals["yang"],
            bmi=a_vals["bmi"],
            whr=a_vals["whr"],
            cwr=a_vals["cwr"],
            shoulder_hip_ratio=a_vals["shr"],
            prescription_tags=tags,
            notes=notes,
        )

    def to_claude_context(self, profile: ConstitutionProfile) -> str:
        """Claude 프롬프트에 삽입할 체질 프로파일 요약 텍스트"""
        return f"""[환자 체질 프로파일]
사상체질 스크리닝:
  태양인 {profile.taeyang_pct}% | 태음인 {profile.taeeum_pct}% | 소양인 {profile.soyang_pct}% | 소음인 {profile.soeum_pct}%
  → 우세 체질: {profile.dominant_type}

한열허실 지수:
  한열(HCI): {profile.hci:+.1f}  ({
    '寒' if profile.hci <= -2 else '熱' if profile.hci >= 2 else '平'
  })
  허실(DEI): {profile.dei:+.1f}  ({
    '虛' if profile.dei <= -2 else '實' if profile.dei >= 2 else '中'
  })

기혈음양 프로파일 (0~10, 높을수록 부족):
  기허 {profile.qi_deficiency} | 혈허 {profile.blood_deficiency} | 음허 {profile.yin_deficiency} | 양허 {profile.yang_deficiency}

체형 지수:
  BMI {profile.bmi} ({
    '저체중' if profile.bmi < 18.5 else '정상' if profile.bmi < 23 else '과체중' if profile.bmi < 25 else '비만'
  }) | WHR {profile.whr} | 흉복비 {profile.cwr} | 어깨/골반 {profile.shoulder_hip_ratio}

처방 선택 태그: {', '.join(profile.prescription_tags)}
임상 노트:
{chr(10).join(f'  · {n}' for n in profile.notes)}"""
