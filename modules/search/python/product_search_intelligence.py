"""Semantic query expansion and ranking for product/service search."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
import json
import re
from typing import Callable

import requests as req


TOKEN_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)
SPACES_RE = re.compile(r"\s+")

RUS_STOPWORDS = {
    "и", "в", "во", "на", "по", "для", "или", "а", "но", "не", "что", "как",
    "от", "до", "из", "за", "под", "над", "к", "ко", "с", "со", "у", "о", "об",
    "про", "это", "тот", "эта", "эти", "без", "при", "где", "кто", "когда",
    "магазин", "услуга", "услуги", "купить", "заказать", "цена", "стоимость",
}

ENG_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "these", "those",
    "shop", "store", "service", "price", "buy", "order",
}

RUS_SUFFIXES = (
    "иями", "ями", "ами", "иями", "ами", "ого", "ему", "ому", "ее", "ие",
    "ые", "ое", "ей", "ий", "ый", "ой", "ая", "яя", "ую", "юю", "ов", "ев",
    "ам", "ям", "ах", "ях", "ом", "ем", "ую", "юю", "ия", "ья", "ии", "ьи",
    "а", "я", "ы", "и", "е", "о", "у", "ю", "ь",
)

ENG_SUFFIXES = ("ingly", "edly", "ing", "ers", "ies", "ed", "er", "es", "s", "ly")

MATCH_LEVEL_ORDER = {
    "exact": 0,
    "synonym": 1,
    "category": 2,
    "partial": 3,
    "none": 4,
}

MATCH_LEVEL_WEIGHT = {
    "exact": 120.0,
    "synonym": 85.0,
    "category": 55.0,
    "partial": 25.0,
    "none": 0.0,
}

QUERY_SOURCE_WEIGHT = {
    "exact": 18.0,
    "synonym": 12.0,
    "ollama": 10.0,
    "category": 8.0,
    "partial": 4.0,
}

LEVEL_LABELS = {
    "exact": "Точное совпадение",
    "synonym": "Совпадение по синонимам",
    "category": "Совпадение по категории",
    "partial": "Частичное совпадение",
    "none": "Нет совпадения",
}

SYNONYM_CONCEPTS = {
    "footwear": {
        "category": "Одежда",
        "terms": [
            "обувь", "кроссовки", "кеды", "тапки", "сникеры",
            "ботинки", "туфли", "спортивная обувь",
        ],
        "related": ["магазин обуви", "повседневная обувь", "обувной магазин"],
    },
    "phone": {
        "category": "Электроника",
        "terms": [
            "телефон", "смартфон", "мобила", "мобильник", "мобильный телефон",
            "iphone", "android", "сотовый",
        ],
        "related": ["магазин телефонов", "аксессуары для смартфона", "гаджеты"],
    },
    "outerwear": {
        "category": "Одежда",
        "terms": [
            "куртка", "ветровка", "верхняя одежда", "пальто", "пуховик",
            "парка", "бомбер",
        ],
        "related": ["одежда", "демисезонная одежда", "зимняя одежда"],
    },
    "food_delivery": {
        "category": "Еда",
        "terms": [
            "доставка еды", "еда на дом", "заказ еды", "доставка", "доставка продуктов",
            "доставка еды круглосуточно", "служба доставки",
        ],
        "related": ["ресторан", "кафе", "пицца", "суши", "бургер"],
    },
    "repair": {
        "category": "Услуги",
        "terms": [
            "ремонт", "ремонт под ключ", "мастер", "сервис", "обслуживание",
            "восстановление", "ремонт техники", "ремонт квартир",
        ],
        "related": ["монтаж", "установка", "выезд мастера", "сервисный центр"],
    },
    "beauty": {
        "category": "Красота",
        "terms": [
            "парикмахерская", "салон красоты", "барбершоп", "маникюр",
            "косметолог", "студия красоты",
        ],
        "related": ["стилист", "уход", "макияж", "укладка"],
    },
    "auto": {
        "category": "Авто",
        "terms": [
            "автосервис", "сто", "ремонт авто", "автомастерская",
            "шиномонтаж", "автозапчасти",
        ],
        "related": ["авто", "машина", "техобслуживание", "диагностика"],
    },
}

CATEGORY_KEYWORDS = {
    "Еда": [
        "доставка еды", "ресторан", "кафе", "пицца", "суши", "роллы", "бургер",
        "продукты", "кофейня", "пекарня", "кондитерская",
    ],
    "Одежда": [
        "одежда", "обувь", "кроссовки", "кеды", "ботинки", "туфли",
        "куртка", "ветровка", "верхняя одежда", "аксессуары",
    ],
    "Электроника": [
        "телефон", "смартфон", "мобильник", "ноутбук", "планшет", "компьютер",
        "наушники", "телевизор", "бытовая техника",
    ],
    "Дом и сад": [
        "мебель", "ремонт квартир", "строительство", "сантехника", "окна",
        "двери", "дом", "дача", "сад",
    ],
    "Авто": [
        "автосервис", "авто", "машина", "запчасти", "шиномонтаж", "автосалон",
        "ремонт авто", "прокат авто",
    ],
    "Красота": [
        "салон красоты", "парикмахерская", "барбершоп", "маникюр", "педикюр",
        "косметолог", "массаж", "спа",
    ],
    "Здоровье": [
        "клиника", "больница", "медицинский", "врач", "стоматология", "аптека",
        "лекарства", "медцентр",
    ],
    "Образование": [
        "курсы", "обучение", "школа", "репетитор", "онлайн курсы", "языковая школа",
    ],
    "Услуги": [
        "юрист", "адвокат", "нотариус", "бухгалтер", "аудитор",
        "клининг", "грузоперевозки", "такси", "ремонт",
    ],
    "Бизнес": [
        "бизнес", "консалтинг", "маркетинг", "seo", "smm", "реклама",
        "аутсорсинг", "бухгалтерское обслуживание",
    ],
}

COMMERCIAL_MODIFIERS = [
    "купить",
    "заказать",
    "цена",
    "стоимость",
    "услуги",
    "официальный сайт",
    "каталог",
    "отзывы",
    "контакты",
    "в наличии",
    "с доставкой",
]

VERTICAL_TEMPLATES = (
    "site:2gis.ru {term} {city}",
    "site:yandex.ru/maps {term} {city}",
    "site:avito.ru {term} {city}",
    "site:flamp.ru {term} {city}",
)


@dataclass
class SearchQueryVariant:
    text: str
    source_level: str
    seed_term: str


@dataclass
class ProductSearchProfile:
    query: str
    city: str
    normalized_query: str
    query_tokens: list[str]
    query_token_set: set[str]
    synonym_terms: list[str] = field(default_factory=list)
    related_terms: list[str] = field(default_factory=list)
    category_hints: list[str] = field(default_factory=list)
    ollama_queries: list[str] = field(default_factory=list)
    expanded_terms: list[str] = field(default_factory=list)


def _dedupe_keep_order(items: list[str], max_items: int | None = None) -> list[str]:
    seen = set()
    out = []
    for raw in items:
        value = SPACES_RE.sub(" ", (raw or "").strip())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if max_items is not None and len(out) >= max_items:
            break
    return out


@lru_cache(maxsize=8192)
def _normalize_cached(text: str) -> str:
    normalized = (text or "").lower().replace("ё", "е")
    normalized = re.sub(r"[_/\\|]+", " ", normalized)
    normalized = re.sub(r"[^0-9a-zа-я\s\-]", " ", normalized)
    normalized = SPACES_RE.sub(" ", normalized).strip()
    return normalized


def normalize_text(text: str) -> str:
    return _normalize_cached(text or "")


def stem_token(token: str) -> str:
    token = normalize_text(token)
    if len(token) <= 3:
        return token

    for suffix in RUS_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            token = token[: -len(suffix)]
            break

    if len(token) > 3:
        for suffix in ENG_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                token = token[: -len(suffix)]
                break

    return token


@lru_cache(maxsize=8192)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    normalized = normalize_text(text)
    raw_tokens = TOKEN_RE.findall(normalized)
    tokens = [stem_token(token) for token in raw_tokens if token]
    return tuple(token for token in tokens if token)


def tokenize(text: str) -> list[str]:
    return list(_tokenize_cached(text or ""))


def _term_matches_query(term: str, normalized_query: str, query_tokens: set[str]) -> bool:
    term_normalized = normalize_text(term)
    if not term_normalized:
        return False
    if term_normalized in normalized_query:
        return True
    term_tokens = set(tokenize(term))
    return bool(term_tokens and term_tokens.intersection(query_tokens))


def _detect_category_hints(normalized_query: str, query_token_set: set[str]) -> list[str]:
    hints = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if normalized_keyword and normalized_keyword in normalized_query:
                hints.append(category)
                break
            keyword_tokens = set(tokenize(keyword))
            if keyword_tokens and keyword_tokens.issubset(query_token_set):
                hints.append(category)
                break
    return _dedupe_keep_order(hints)


def _extract_concept_terms(normalized_query: str, query_token_set: set[str]) -> tuple[list[str], list[str], list[str]]:
    synonym_terms: list[str] = []
    related_terms: list[str] = []
    categories: list[str] = []

    for concept in SYNONYM_CONCEPTS.values():
        terms = concept.get("terms", [])
        if not terms:
            continue
        is_match = any(_term_matches_query(term, normalized_query, query_token_set) for term in terms)
        if not is_match:
            continue

        synonym_terms.extend(terms)
        related_terms.extend(concept.get("related", []))
        category = concept.get("category")
        if category:
            categories.append(category)

    return (
        _dedupe_keep_order(synonym_terms, max_items=40),
        _dedupe_keep_order(related_terms, max_items=40),
        _dedupe_keep_order(categories),
    )


def _parse_ollama_queries(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    # 1) Пытаемся распарсить как JSON целиком
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            values = data.get("queries") or data.get("варианты") or []
        elif isinstance(data, list):
            values = data
        else:
            values = []
        return _dedupe_keep_order([str(v) for v in values if isinstance(v, (str, int, float))], max_items=10)
    except Exception:
        pass

    # 2) Ищем JSON-массив внутри ответа
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            arr = json.loads(match.group(0))
            if isinstance(arr, list):
                return _dedupe_keep_order([str(v) for v in arr], max_items=10)
        except Exception:
            pass

    # 3) Парсим нумерованный/маркированный список
    candidates = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[\-\*\d\.\)]\s*", "", line).strip()
        if line:
            candidates.append(line)
    return _dedupe_keep_order(candidates, max_items=10)


def _generate_ollama_queries(
    query: str,
    city: str,
    seed_terms: list[str],
    ollama_url: str,
    ollama_model: str,
    max_variants: int = 6,
    emit: Callable[[str, str], None] | None = None,
) -> list[str]:
    if not ollama_url or not ollama_model:
        return []

    prompt = (
        "Ты помощник по расширению поисковых запросов для e-commerce и услуг.\n"
        "Сгенерируй 6 коротких вариантов запроса на русском языке.\n"
        "Требования:\n"
        "- добавляй синонимы и близкие формулировки;\n"
        "- учитывай коммерческий интент (купить/заказать/услуги/цена);\n"
        "- не добавляй пояснения, только JSON-массив строк.\n\n"
        f"Исходный запрос: {query}\n"
        f"Город/регион: {city or 'не указан'}\n"
        f"Близкие термины: {', '.join(seed_terms[:12])}"
    )

    payload = {
        "model": ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 220},
    }
    try:
        response = req.post(f"{ollama_url.rstrip('/')}/api/chat", json=payload, timeout=25)
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        queries = _parse_ollama_queries(content)
        queries = [q for q in queries if 3 <= len(q) <= 140]
        queries = _dedupe_keep_order(queries, max_items=max_variants)
        if emit and queries:
            emit(f"🤖 Ollama сгенерировала {len(queries)} дополнительных запросов", "info")
        return queries
    except Exception as exc:
        if emit:
            emit(f"⚠️ Ollama недоступна для расширения запроса: {str(exc)[:80]}", "warn")
        return []


def build_search_profile(
    query: str,
    city: str = "",
    use_ollama: bool = False,
    ollama_url: str = "",
    ollama_model: str = "",
    max_ollama_variants: int = 6,
    manual_terms: list[str] | None = None,
    emit: Callable[[str, str], None] | None = None,
) -> ProductSearchProfile:
    normalized_query = normalize_text(query)
    query_tokens = tokenize(query)
    query_token_set = set(query_tokens)

    synonym_terms, related_terms, concept_categories = _extract_concept_terms(
        normalized_query, query_token_set
    )
    category_hints = _detect_category_hints(normalized_query, query_token_set)
    category_hints = _dedupe_keep_order(category_hints + concept_categories)

    if manual_terms:
        synonym_terms = _dedupe_keep_order(synonym_terms + manual_terms, max_items=50)

    expanded_terms = _dedupe_keep_order(
        [query]
        + synonym_terms
        + related_terms
        + query_tokens
        + category_hints,
        max_items=80,
    )

    ollama_queries: list[str] = []
    if use_ollama:
        ollama_queries = _generate_ollama_queries(
            query=query,
            city=city,
            seed_terms=expanded_terms,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            max_variants=max_ollama_variants,
            emit=emit,
        )
        expanded_terms = _dedupe_keep_order(expanded_terms + ollama_queries, max_items=90)

    return ProductSearchProfile(
        query=query.strip(),
        city=(city or "").strip(),
        normalized_query=normalized_query,
        query_tokens=query_tokens,
        query_token_set=query_token_set,
        synonym_terms=synonym_terms,
        related_terms=related_terms,
        category_hints=category_hints,
        ollama_queries=ollama_queries,
        expanded_terms=expanded_terms,
    )


def build_search_queries(profile: ProductSearchProfile, max_queries: int = 60) -> list[SearchQueryVariant]:
    by_source: dict[str, list[str]] = {
        "exact": [profile.query],
        "synonym": profile.synonym_terms[:14],
        "category": profile.category_hints[:6],
        "partial": profile.query_tokens[:8],
        "ollama": profile.ollama_queries[:8],
    }

    raw_variants: list[SearchQueryVariant] = []
    city = profile.city.strip()

    for source_level, terms in by_source.items():
        if not terms:
            continue

        # Для exact/synonym добавляем коммерческие хвосты
        modifiers = COMMERCIAL_MODIFIERS if source_level in {"exact", "synonym", "ollama"} else []

        for term in terms:
            base_term = SPACES_RE.sub(" ", (term or "").strip())
            if not base_term:
                continue

            raw_variants.append(SearchQueryVariant(text=base_term, source_level=source_level, seed_term=base_term))

            if city:
                raw_variants.append(
                    SearchQueryVariant(text=f"{base_term} {city}", source_level=source_level, seed_term=base_term)
                )

            for modifier in modifiers[:5]:
                raw_variants.append(
                    SearchQueryVariant(
                        text=f"{base_term} {modifier}",
                        source_level=source_level,
                        seed_term=base_term,
                    )
                )
                if city:
                    raw_variants.append(
                        SearchQueryVariant(
                            text=f"{base_term} {city} {modifier}",
                            source_level=source_level,
                            seed_term=base_term,
                        )
                    )

            if city and source_level in {"exact", "synonym", "ollama"}:
                for template in VERTICAL_TEMPLATES:
                    raw_variants.append(
                        SearchQueryVariant(
                            text=template.format(term=base_term, city=city).strip(),
                            source_level=source_level,
                            seed_term=base_term,
                        )
                    )

    # Убираем дубли и оставляем более приоритетный source_level
    priority = {"exact": 0, "synonym": 1, "ollama": 2, "category": 3, "partial": 4}
    best_by_query: dict[str, SearchQueryVariant] = {}

    for item in raw_variants:
        normalized = normalize_text(item.text)
        if not normalized:
            continue
        existing = best_by_query.get(normalized)
        if existing is None or priority.get(item.source_level, 99) < priority.get(existing.source_level, 99):
            best_by_query[normalized] = item

    ordered = sorted(best_by_query.values(), key=lambda x: (priority.get(x.source_level, 99), len(x.text)))
    return ordered[:max(10, max_queries)]


def classify_product_category(text: str) -> str:
    normalized = normalize_text(text)
    token_set = set(tokenize(text))
    if not normalized and not token_set:
        return "Другое"

    best_category = "Другое"
    best_score = 0.0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            keyword_norm = normalize_text(keyword)
            if keyword_norm and keyword_norm in normalized:
                score += 2.5
                continue

            kw_tokens = set(tokenize(keyword))
            if kw_tokens and kw_tokens.issubset(token_set):
                score += 1.8
            elif kw_tokens and kw_tokens.intersection(token_set):
                score += 0.7

        if score > best_score:
            best_score = score
            best_category = category

    return best_category if best_score > 0 else "Другое"


def _has_term_match(term: str, normalized_text: str, token_set: set[str]) -> bool:
    normalized_term = normalize_text(term)
    if normalized_term and normalized_term in normalized_text:
        return True
    term_tokens = set(tokenize(term))
    return bool(term_tokens and term_tokens.issubset(token_set))


def _extract_tags(text: str, category: str, limit: int = 8) -> list[str]:
    normalized = normalize_text(text)
    token_list = tokenize(text)
    token_counter = Counter(token for token in token_list if len(token) >= 4)

    tags: list[str] = []
    if category and category != "Другое":
        tags.append(category.lower())

    for concept in SYNONYM_CONCEPTS.values():
        for term in concept.get("terms", []):
            if _has_term_match(term, normalized, set(token_list)):
                tags.append(term)

    for token, _ in token_counter.most_common(limit * 2):
        if token in RUS_STOPWORDS or token in ENG_STOPWORDS:
            continue
        tags.append(token)
        if len(tags) >= limit:
            break

    return _dedupe_keep_order(tags, max_items=limit)


def score_result_match(
    title: str,
    description: str,
    profile: ProductSearchProfile,
    query_source: str = "partial",
    city: str = "",
) -> dict:
    title = (title or "").strip()
    description = (description or "").strip()
    combined_text = f"{title} {description}".strip()
    normalized_combined = normalize_text(combined_text)
    token_set = set(tokenize(combined_text))
    normalized_title = normalize_text(title)

    category = classify_product_category(combined_text)
    tags = _extract_tags(combined_text, category, limit=8)
    category_hints = set(profile.category_hints)

    exact_match = False
    if profile.normalized_query and profile.normalized_query in normalized_combined:
        exact_match = True
    elif profile.query_token_set and profile.query_token_set.issubset(token_set):
        exact_match = True

    matched_synonyms = [
        term for term in profile.synonym_terms
        if _has_term_match(term, normalized_combined, token_set)
    ]
    matched_related = [
        term for term in profile.related_terms
        if _has_term_match(term, normalized_combined, token_set)
    ]

    category_match = bool(category in category_hints and category != "Другое")
    token_overlap = len(profile.query_token_set.intersection(token_set))
    partial_match = token_overlap > 0

    if exact_match:
        match_level = "exact"
    elif matched_synonyms:
        match_level = "synonym"
    elif category_match:
        match_level = "category"
    elif partial_match:
        match_level = "partial"
    else:
        match_level = "none"

    base = MATCH_LEVEL_WEIGHT.get(match_level, 0.0)
    source_weight = QUERY_SOURCE_WEIGHT.get(query_source, 0.0)
    overlap_score = token_overlap * 6.0
    synonym_score = min(18.0, len(matched_synonyms) * 4.0)
    related_score = min(10.0, len(matched_related) * 2.0)
    title_bonus = 8.0 if profile.normalized_query and profile.normalized_query in normalized_title else 0.0
    city_bonus = 5.0 if city and normalize_text(city) in normalized_combined else 0.0

    rank_score = round(base + source_weight + overlap_score + synonym_score + related_score + title_bonus + city_bonus, 2)

    return {
        "match_level": match_level,
        "match_label": LEVEL_LABELS.get(match_level, LEVEL_LABELS["none"]),
        "rank_score": rank_score,
        "token_overlap": token_overlap,
        "matched_synonyms": _dedupe_keep_order(matched_synonyms, max_items=8),
        "related_terms": _dedupe_keep_order(matched_related, max_items=8),
        "category": category,
        "tags": tags,
    }
