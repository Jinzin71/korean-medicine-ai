"""
pubmed_search.py — PubMed E-utilities 무료 API 기반 논문 검색
=========================================================
API 키 불필요. NCBI E-utilities (esearch + efetch) 사용.
https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

import re
import requests
from typing import Optional

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# 처방 영문명 매핑 (주요 처방)
PRESCRIPTION_EN = {
    "소청룡탕": "Socheongryong-tang OR Xiao Qing Long Tang OR Minor Blue Dragon",
    "보중익기탕": "Bojungikgi-tang OR Bu Zhong Yi Qi Tang",
    "갈근탕": "Galgeun-tang OR Ge Gen Tang OR Pueraria decoction",
    "반하사심탕": "Banhasasim-tang OR Ban Xia Xie Xin Tang",
    "소시호탕": "Sosihoo-tang OR Xiao Chai Hu Tang OR Minor Bupleurum",
    "오령산": "Oryeong-san OR Wu Ling San OR Five Ingredient Powder",
    "사물탕": "Samul-tang OR Si Wu Tang OR Four Substance",
    "육미지황탕": "Yukmijihwang-tang OR Liu Wei Di Huang Wan",
    "팔미지황탕": "Palmijihwang-tang OR Ba Wei Di Huang Wan OR Hachimi",
    "쌍화탕": "Ssanghwa-tang OR Shuanghe Tang",
    "형방패독산": "Hyeongbangpaedok-san OR Jing Fang Bai Du San",
    "대시호탕": "Daesihoo-tang OR Da Chai Hu Tang OR Major Bupleurum",
    "귀비탕": "Gwibi-tang OR Gui Pi Tang",
    "십전대보탕": "Sipjeondaebo-tang OR Shi Quan Da Bu Tang",
    "삼소음": "Samsoin OR Shen Su Yin",
    "황련해독탕": "Hwangnyeonhaedok-tang OR Huang Lian Jie Du Tang",
    "온백원": "Onbaekwon",
    "당귀수산": "Dangguisu-san OR Dang Gui Xu San",
    "이중탕": "Ijung-tang OR Li Zhong Tang",
    "사군자탕": "Sagunja-tang OR Si Jun Zi Tang OR Four Gentlemen",
    "생맥산": "Saengmaek-san OR Sheng Mai San",
    "마황탕": "Mahwang-tang OR Ma Huang Tang OR Ephedra decoction",
    "계지탕": "Gyeji-tang OR Gui Zhi Tang OR Cinnamon Twig",
    "인삼패독산": "Insampaedok-san OR Ren Shen Bai Du San",
    "청폐사간탕": "Cheongpyesagan-tang",
}


def _get_en_name(presc_name: str) -> str:
    """처방의 영문 검색어 반환"""
    if presc_name in PRESCRIPTION_EN:
        return PRESCRIPTION_EN[presc_name]
    # 한글 → 기본 로마자 변환 시도 (처방명 그대로)
    return presc_name


def _search_ids(query: str, max_results: int = 10) -> list[str]:
    """PubMed에서 PMID 목록 검색"""
    try:
        resp = requests.get(ESEARCH_URL, params={
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }, timeout=15)
        data = resp.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []


def _fetch_abstracts(pmids: list[str]) -> list[dict]:
    """PMID 목록으로 논문 상세 정보 가져오기"""
    if not pmids:
        return []
    try:
        resp = requests.get(EFETCH_URL, params={
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }, timeout=20)
        return _parse_pubmed_xml(resp.text)
    except Exception:
        return []


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """PubMed XML에서 논문 정보 추출 (간단한 regex 파싱)"""
    articles = []
    # 각 <PubmedArticle> 블록 추출
    blocks = re.findall(r"<PubmedArticle>(.*?)</PubmedArticle>", xml_text, re.DOTALL)
    for block in blocks:
        pmid = _extract(block, r"<PMID[^>]*>(\d+)</PMID>")
        title = _extract(block, r"<ArticleTitle>(.*?)</ArticleTitle>")
        abstract = _extract(block, r"<AbstractText[^>]*>(.*?)</AbstractText>")
        journal = _extract(block, r"<Title>(.*?)</Title>")
        year = _extract(block, r"<Year>(\d{4})</Year>")
        # 저자
        authors = re.findall(r"<LastName>(.*?)</LastName>", block)
        author_str = ", ".join(authors[:3])
        if len(authors) > 3:
            author_str += " et al."

        if title:
            # HTML 태그 제거
            title = re.sub(r"<[^>]+>", "", title)
            abstract = re.sub(r"<[^>]+>", "", abstract) if abstract else ""
            articles.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract[:500],
                "journal": journal or "",
                "year": year or "",
                "authors": author_str,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            })
    return articles


def _extract(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1).strip() if m else ""


def search_pubmed(presc_name: str, condition: str) -> str:
    """처방 + 질환으로 PubMed 검색 → 마크다운 결과"""
    en_name = _get_en_name(presc_name)
    query = f"({en_name}) AND ({condition} OR Korean medicine OR herbal medicine)"

    pmids = _search_ids(query, max_results=8)

    if not pmids:
        # fallback: 영문명만으로 재검색
        pmids = _search_ids(f"({en_name}) AND herbal medicine", max_results=5)

    if not pmids:
        return (
            f"## {presc_name} + {condition} — PubMed 검색 결과\n\n"
            f"검색 결과가 없습니다.\n\n"
            f"**검색어:** `{query}`\n\n"
            f"PubMed에 해당 처방의 영문 논문이 등록되지 않았을 수 있습니다.\n"
            f"[PubMed에서 직접 검색](https://pubmed.ncbi.nlm.nih.gov/?term={requests.utils.quote(query)})"
        )

    articles = _fetch_abstracts(pmids)

    sections = [f"## {presc_name} + {condition} — PubMed 검색 결과\n"]
    sections.append(f"총 **{len(articles)}편** 논문\n")

    for i, a in enumerate(articles, 1):
        sections.append(f"### {i}. {a['title']}")
        meta = []
        if a["authors"]:
            meta.append(a["authors"])
        if a["journal"]:
            meta.append(f"*{a['journal']}*")
        if a["year"]:
            meta.append(f"({a['year']})")
        sections.append(" — ".join(meta))

        if a["abstract"]:
            sections.append(f"\n> {a['abstract']}{'...' if len(a['abstract'])>=500 else ''}")

        if a["url"]:
            sections.append(f"\n[PubMed 원문]({a['url']})")
        sections.append("")

    sections.append(f"\n---\n[PubMed에서 더 검색](https://pubmed.ncbi.nlm.nih.gov/?term={requests.utils.quote(query)})")
    return "\n".join(sections)


def search_pubmed_by_symptom(symptoms: str, candidate_names: Optional[list] = None,
                              db=None) -> str:
    """증상 기반 → 후보 처방들의 논문 근거 검색"""
    if candidate_names:
        names = candidate_names
    elif db:
        # DB에서 증상 매칭 처방 상위 5개 가져오기
        matches = db.search_by_symptoms(symptoms)
        names = [p.name for p in matches[:5]]
    else:
        return "처방 목록 또는 DB가 필요합니다."

    if not names:
        return f"**'{symptoms}'**에 해당하는 처방을 찾지 못했습니다."

    sections = [f"## 「{symptoms}」 근거 기반 처방 검색\n"]
    sections.append(f"검색 대상 처방: {', '.join(names)}\n")

    for name in names[:5]:
        en_name = _get_en_name(name)
        query = f"({en_name}) AND ({symptoms} OR clinical trial OR herbal)"
        pmids = _search_ids(query, max_results=3)
        articles = _fetch_abstracts(pmids) if pmids else []

        sections.append(f"---\n### {name}")
        if articles:
            sections.append(f"논문 {len(articles)}편:\n")
            for a in articles:
                sections.append(f"- **{a['title']}** ({a['year']}) — {a['authors']}")
                if a["url"]:
                    sections.append(f"  [PubMed]({a['url']})")
        else:
            sections.append("PubMed 검색 결과 없음")
        sections.append("")

    return "\n".join(sections)
