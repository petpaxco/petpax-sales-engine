"""Rows below mirror the real tracker's Accounts tab layout (values abbreviated)."""
from petpax_engine.tracker_import import map_accounts, summarize

HEADER = ["Account / Shop Name", "Contact Name", "Contact Role", "Email", "Phone", "Website",
          "Street Address", "City", "State", "ZIP", "Country", "Region", "Account Type", "Lead Source",
          "Owner", "Next Action", "Next Action Date", "Stage", "Products Carried", "First Order",
          "Last Order", "# Orders", "Lifetime Revenue", "Avg Order", "Days Since Order", "Reorder Due",
          "Account Health", "Last Contact", "Days Since Contact", "Follow-Up Status", "Notes"]


def row(**kw):
    r = dict.fromkeys(HEADER, "")
    r.update(kw)
    return [r[h] for h in HEADER]


ROWS = [HEADER,
        row(**{"Account / Shop Name": "Mountain Dog Lounge", "Email": "admin@mountaindoglounge.com",
               "Phone": "(385) 312-0515", "Street Address": "464 N Main Street", "City": "Heber City",
               "State": "UT", "ZIP": "84032", "Country": "USA", "Account Type": "Daycare / Boarding",
               "Stage": "6 - Repeat Customer", "First Order": "10/14/25", "Last Order": "10/9/26",
               "# Orders": "3", "Lifetime Revenue": "$730.18", "Avg Order": "$243.39", "Account Health": "Healthy"}),
        row(**{"Account / Shop Name": "Primp My Paws", "Email": "primpmypaws@gmail.com",
               "Street Address": "32 Cedar St", "City": "Dobbs Ferry", "State": "NY", "ZIP": "10522",
               "Country": "USA", "Stage": "5 - First Order", "# Orders": "1", "Lifetime Revenue": "$168.00",
               "Account Health": "Check Order Dates"}),
        row(**{"Account / Shop Name": "Bath and Biscuits", "Email": "Lisa@bathandbiscuits.com",
               "City": "Sacramento", "State": "CA", "Country": "USA", "Stage": "5 - First Order",
               "# Orders": "0", "Lifetime Revenue": "-"}),
        row(**{"Account / Shop Name": "Katy Matute (no shop name)", "Email": "katymatute14@yahoo.com",
               "Country": "Honduras", "Account Type": "Individual / Other", "Stage": "5 - First Order",
               "First Order": "3/25/26", "Last Order": "3/25/26", "# Orders": "1", "Lifetime Revenue": "$178.50",
               "Account Health": "Lapsed"}),
        row(**{"Account / Shop Name": "The Bougie Baby Pet Salon", "Email": "joe@thebougiebaby.shop",
               "Phone": "+1 760-953-3012", "City": "Hesperia", "State": "CA", "Stage": "3 - Interested",
               "Owner": "Nathan"}),
        row(**{"Account / Shop Name": "Zoomin Groomin", "Email": "dina@zoomingroomin.com",
               "Stage": "Closed - Lost"}),
        ]


def test_map_accounts():
    recs = {r.name: r for r in map_accounts(ROWS)}
    mdl = recs["Mountain Dog Lounge"]
    assert mdl.stage == "active_account" and mdl.account["lifetime_revenue"] == 730.18
    assert mdl.account["owner"] == "anthony" and "owner blank (defaulted to Anthony)" in mdl.issues
    assert mdl.business["source_ref"].endswith("Accounts!A2")
    assert "order dates missing" in recs["Primp My Paws"].issues
    bb = recs["Bath and Biscuits"]
    assert bb.account is None and bb.stage == "engaged"
    assert "marked as customer but 0 orders recorded" in bb.issues
    km = recs["Katy Matute (no shop name)"]
    assert km.business["type"] == "individual" and any("international" in i for i in km.issues)
    assert km.account["status"] == "inactive"
    assert recs["The Bougie Baby Pet Salon"].stage == "engaged"
    assert recs["Zoomin Groomin"].stage == "lost"
    assert all(r.exclude_from_cold for r in recs.values())


def test_summary():
    s = summarize(map_accounts(ROWS))
    assert s == {"rows": 6, "active_accounts": 3, "leads": 2, "lost": 1, "with_issues": 6, "california": 2}
