from datetime import date

from petpax_engine.dedup import Candidate, find_duplicates
from petpax_engine.normalize import email_domain, normalize_name, phone_digits, website_domain
from petpax_engine.places import parse_place
from petpax_engine.reorder import estimate, is_reorder_due
from petpax_engine.scoring import LeadInputs, score_lead
from petpax_engine.territory import assign_territory, miles_from_base, visit_candidate

TODAY = date(2026, 11, 10)


# ---------------------------------------------------------------- normalize
def test_normalize():
    assert normalize_name("The Dapper Dog Salon, LLC") == "dapper"
    assert normalize_name("Wash N' Wags") == "wash n wags"
    assert website_domain("www.DoggieBeachBoutique.com/") == "doggiebeachboutique.com"
    assert email_domain("lia@thedapperdogsalon.com") == "thedapperdogsalon.com"
    assert email_domain("someone@gmail.com") is None
    assert phone_digits("(385) 312-0515") == "3853120515"
    assert phone_digits("336-540-1600\nAlt phone 336-540-1400 ext 100") == "3365401600"
    assert phone_digits("+1 760-953-3012") == "7609533012"
    assert phone_digits("62(812)-1213-9923") is None


# -------------------------------------------------------------------- dedup
def test_dedup_merges_same_email_domain_and_flags_similar_names():
    cands = [
        Candidate("r1", "The Woof Wash", "29 Essex Street", "Melrose", "02176", emails="admin@woofwashgrooming.com"),
        Candidate("r2", "Woof Wash Grooming", None, "Melrose", "02176", emails="admin@woofwashgrooming.com"),
        Candidate("r3", "Zen Paw Spa", "1 Main St", "Lunenburg", "01462", emails="zenpawspa@gmail.com"),
        Candidate("r4", "ZenPaw Spa & Grooming", "1 Main Street", "Lunenburg", "01462"),
        Candidate("r5", "Paws & Rec", "857 4th Avenue", "Brooklyn", "11232", emails="fun@pawsandrec.com"),
        Candidate("r6", "Glamour Paws", "10 Pine", "LA", "90008", phone="(310) 555-0100"),
        Candidate("r7", "Glamour Paws Mobile", None, "LA", "90016", phone="310.555.0100"),
        Candidate("r8", "Happy Tails", None, "Pasadena", "91101", emails="a@gmail.com"),
        Candidate("r9", "Lucky Tails", None, "Pasadena", "91101", emails="b@gmail.com"),
    ]
    res = find_duplicates(cands)
    auto = {(m.a, m.b, m.reason) for m in res.auto}
    assert ("r1", "r2", "same website/email domain") in auto
    assert ("r3", "r4", "same street address") in auto      # "St" == "Street"
    assert ("r6", "r7", "same phone") in auto
    pairs = {(m.a, m.b) for m in res.matches}
    assert ("r8", "r9") not in pairs                       # shared gmail is not evidence
    assert all("r5" not in p for p in pairs)


def test_fuzzy_name_goes_to_review_not_auto():
    res = find_duplicates([Candidate("a", "Bark Avenue Grooming", city="Torrance", zip="90501"),
                           Candidate("b", "Bark Avenue Pet Salon", city="Torrance", zip="90501")])
    assert len(res.review) == 1 and not res.auto


# ---------------------------------------------------------------- territory
def test_territory():
    assert assign_territory("CA", "Los Angeles County") == ("LA County", 1)
    assert assign_territory("CA", "San Bernardino") == ("Inland Empire", 1)
    assert assign_territory("CA", "Sacramento") == ("Rest of California", 2)
    assert assign_territory("NV", None) == ("Regional expansion", 3)
    assert assign_territory("NY", None) == (None, None)
    # Santa Monica ~8 mi, Hesperia ~70 mi straight-line from 90008
    assert miles_from_base(34.0195, -118.4912) < 12
    assert visit_candidate(34.4264, -117.3009) is False
    assert visit_candidate(None, None, drive_minutes=40) is True


# ------------------------------------------------------------------ scoring
def test_scoring_explainable_and_missing_is_neutral():
    hot = score_lead(LeadInputs(phase=1, drive_minutes=25, business_type="salon",
                                offers_relevant_services=True, has_business_email=True, has_phone=True,
                                has_decision_maker=True, sourced_fact_count=3, review_count=180, rating=4.8))
    assert hot.total >= 80 and hot.band == "High priority"
    assert set(hot.parts) == {"geo", "fit", "contact_quality", "personalization", "potential"}
    assert any("min drive" in r for r in hot.reasons["geo"])
    unknown_size = score_lead(LeadInputs(phase=1, business_type="salon"))
    assert unknown_size.parts["potential"] == round(0.5 * 15)
    assert score_lead(LeadInputs(phase=None)).parts["geo"] == 0


# ------------------------------------------------------------------ reorder
def test_reorder_estimates():
    e = estimate([date(2025, 10, 14), date(2026, 3, 1), date(2026, 10, 9)], TODAY)
    assert e.basis == "own_median" and e.status == "Healthy"
    one = estimate([date(2026, 8, 13)], TODAY)          # Holistic For Pets pattern
    assert one.basis == "default_cycle" and one.next_reorder == date(2026, 11, 11)
    assert one.status == "Reorder Soon" and is_reorder_due(one)
    lapsed = estimate([date(2025, 8, 18)], TODAY)
    assert lapsed.status == "Lapsed"
    none = estimate([None], TODAY)
    assert none.status == "Check order dates" and none.next_reorder is None


# ------------------------------------------------------------------- places
def test_parse_place():
    p = parse_place({
        "id": "ChIJabc", "displayName": {"text": "Bark Avenue Grooming"},
        "formattedAddress": "123 W Manchester Blvd, Inglewood, CA 90301, USA",
        "addressComponents": [
            {"longText": "123", "types": ["street_number"]},
            {"longText": "West Manchester Boulevard", "types": ["route"]},
            {"longText": "Inglewood", "types": ["locality"]},
            {"longText": "Los Angeles County", "types": ["administrative_area_level_2"]},
            {"longText": "California", "shortText": "CA", "types": ["administrative_area_level_1"]},
            {"longText": "90301", "types": ["postal_code"]}],
        "location": {"latitude": 33.96, "longitude": -118.36},
        "nationalPhoneNumber": "(310) 555-0199", "websiteUri": "https://barkavenue.example",
        "rating": 4.7, "userRatingCount": 212, "businessStatus": "OPERATIONAL"})
    assert (p.city, p.county, p.state, p.zip) == ("Inglewood", "Los Angeles", "CA", "90301")
    assert p.operational and p.review_count == 212
