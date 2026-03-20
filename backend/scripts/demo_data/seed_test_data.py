"""
Seed comprehensive test data for Budget, Financial, Gantt Chart, and Kanban features.
Run from backend/ directory:  python -m scripts.demo_data.seed_test_data
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./pms_dev.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

def seed():
    db = Session()
    now = datetime.utcnow()
    try:
        # ========================================================
        # 1. ADDITIONAL TASKS (for Gantt & Kanban - multiple per project)
        # ========================================================
        # Check existing max task id
        max_task = db.execute(text("SELECT MAX(id) FROM tasks")).scalar() or 0
        print(f"Current max task ID: {max_task}")

        # We'll add tasks to projects 1, 2, 3 (the most active ones)
        new_tasks = []
        tid = max_task + 1

        # --- Project 1: Mobile App Redesign (8 additional tasks) ---
        p1_tasks = [
            (tid,   "Wireframe user flows",          1, 2, "done",        "high",     now - timedelta(days=20), now - timedelta(days=10), 8.0,  8.0, 100),
            (tid+1, "Design system components",       1, 3, "done",        "high",     now - timedelta(days=18), now - timedelta(days=5),  12.0, 11.0, 100),
            (tid+2, "Implement navigation shell",     1, 5, "done",        "medium",   now - timedelta(days=12), now - timedelta(days=2),  16.0, 14.0, 100),
            (tid+3, "Build authentication screens",   1, 6, "in_progress", "critical", now - timedelta(days=8),  now + timedelta(days=5),  20.0, 12.0, 60),
            (tid+4, "Integrate REST API layer",       1, 7, "in_progress", "high",     now - timedelta(days=5),  now + timedelta(days=10), 24.0, 8.0,  35),
            (tid+5, "Implement push notifications",   1, 8, "todo",        "medium",   now + timedelta(days=2),  now + timedelta(days=15), 12.0, 0.0,  0),
            (tid+6, "Performance optimization",       1, 9, "todo",        "high",     now + timedelta(days=10), now + timedelta(days=22), 16.0, 0.0,  0),
            (tid+7, "App store submission prep",      1, 10,"todo",        "low",      now + timedelta(days=20), now + timedelta(days=30), 8.0,  0.0,  0),
        ]
        for t in p1_tasks:
            new_tasks.append(t)

        # --- Project 2: Backend API Optimization (6 additional tasks) ---
        base = tid + 8
        p2_tasks = [
            (base,   "Profile slow endpoints",         2, 4, "done",        "critical", now - timedelta(days=25), now - timedelta(days=18), 10.0, 12.0, 100),
            (base+1, "Optimize database queries",      2, 5, "done",        "critical", now - timedelta(days=18), now - timedelta(days=8),  20.0, 18.0, 100),
            (base+2, "Implement caching layer",        2, 6, "in_progress", "high",     now - timedelta(days=10), now + timedelta(days=3),  16.0, 10.0, 65),
            (base+3, "Add connection pooling",         2, 7, "in_progress", "medium",   now - timedelta(days=5),  now + timedelta(days=8),  12.0, 4.0,  30),
            (base+4, "Load testing & benchmarks",      2, 8, "todo",        "high",     now + timedelta(days=5),  now + timedelta(days=15), 14.0, 0.0,  0),
            (base+5, "Deploy optimized APIs",          2, 9, "todo",        "medium",   now + timedelta(days=12), now + timedelta(days=20), 8.0,  0.0,  0),
        ]
        for t in p2_tasks:
            new_tasks.append(t)

        # --- Project 3: Database Migration (6 additional tasks) ---
        base2 = base + 6
        p3_tasks = [
            (base2,   "Audit current schema",            3, 3, "done",        "high",     now - timedelta(days=22), now - timedelta(days=15), 8.0,  10.0, 100),
            (base2+1, "Design new schema",               3, 4, "done",        "critical", now - timedelta(days=15), now - timedelta(days=8),  12.0, 14.0, 100),
            (base2+2, "Write migration scripts",         3, 5, "in_progress", "critical", now - timedelta(days=8),  now + timedelta(days=4),  20.0, 12.0, 55),
            (base2+3, "Test migration on staging",       3, 6, "todo",        "high",     now + timedelta(days=2),  now + timedelta(days=10), 16.0, 0.0,  0),
            (base2+4, "Data validation & verification",  3, 7, "todo",        "medium",   now + timedelta(days=8),  now + timedelta(days=15), 12.0, 0.0,  0),
            (base2+5, "Production cutover",              3, 8, "todo",        "critical", now + timedelta(days=14), now + timedelta(days=18), 10.0, 0.0,  0),
        ]
        for t in p3_tasks:
            new_tasks.append(t)

        # --- Project 5: Security Audit (4 additional tasks) ---
        base3 = base2 + 6
        p5_tasks = [
            (base3,   "Vulnerability scanning",      5, 4, "done",        "critical", now - timedelta(days=15), now - timedelta(days=8),  12.0, 14.0, 100),
            (base3+1, "Penetration testing",         5, 6, "in_progress", "critical", now - timedelta(days=8),  now + timedelta(days=5),  20.0, 10.0, 50),
            (base3+2, "Security patch deployment",   5, 7, "todo",        "high",     now + timedelta(days=3),  now + timedelta(days=12), 16.0, 0.0,  0),
            (base3+3, "Compliance documentation",    5, 9, "todo",        "medium",   now + timedelta(days=10), now + timedelta(days=20), 10.0, 0.0,  0),
        ]
        for t in p5_tasks:
            new_tasks.append(t)

        # Insert all tasks
        for t in new_tasks:
            db.execute(text("""
                INSERT INTO tasks (id, title, project_id, assignee_id, status, priority, created_at, due_date, estimated_hours, actual_hours, progress)
                VALUES (:id, :title, :pid, :aid, :status, :priority, :created, :due, :est, :act, :prog)
            """), {
                "id": t[0], "title": t[1], "pid": t[2], "aid": t[3],
                "status": t[4], "priority": t[5],
                "created": t[6].isoformat(), "due": t[7].isoformat(),
                "est": t[8], "act": t[9], "prog": t[10]
            })
        print(f"Inserted {len(new_tasks)} new tasks (IDs {max_task+1} to {new_tasks[-1][0]})")

        # ========================================================
        # 2. TASK DEPENDENCIES (for Gantt critical path)
        # ========================================================
        # Project 1 chain: existing task 1 -> wireframe -> design system -> nav shell -> auth screens -> API layer -> push notifs -> perf opt -> app store
        p1_deps = [
            (1,          tid,   "finish_to_start"),   # Design homepage -> Wireframe user flows
            (tid,        tid+1, "finish_to_start"),   # Wireframe -> Design system
            (tid+1,      tid+2, "finish_to_start"),   # Design system -> Nav shell
            (tid+2,      tid+3, "finish_to_start"),   # Nav shell -> Auth screens
            (tid+3,      tid+4, "finish_to_start"),   # Auth screens -> API layer
            (tid+4,      tid+5, "finish_to_start"),   # API layer -> Push notifs
            (tid+5,      tid+6, "finish_to_start"),   # Push notifs -> Perf optimization
            (tid+6,      tid+7, "finish_to_start"),   # Perf opt -> App store
        ]
        # Project 2 chain: existing task 2 -> profile -> optimize DB -> caching -> connection pooling -> load test -> deploy
        p2_deps = [
            (2,          base,   "finish_to_start"),
            (base,       base+1, "finish_to_start"),
            (base+1,     base+2, "finish_to_start"),
            (base+2,     base+3, "finish_to_start"),
            (base+3,     base+4, "finish_to_start"),
            (base+4,     base+5, "finish_to_start"),
        ]
        # Project 3 chain: existing task 3 -> audit -> design schema -> migration scripts -> test staging -> validate -> cutover
        p3_deps = [
            (3,          base2,   "finish_to_start"),
            (base2,      base2+1, "finish_to_start"),
            (base2+1,    base2+2, "finish_to_start"),
            (base2+2,    base2+3, "finish_to_start"),
            (base2+3,    base2+4, "finish_to_start"),
            (base2+4,    base2+5, "finish_to_start"),
        ]
        # Project 5 chain
        p5_deps = [
            (5,          base3,   "finish_to_start"),
            (base3,      base3+1, "finish_to_start"),
            (base3+1,    base3+2, "finish_to_start"),
            (base3+2,    base3+3, "finish_to_start"),
        ]

        all_deps = p1_deps + p2_deps + p3_deps + p5_deps
        for d in all_deps:
            db.execute(text("""
                INSERT OR IGNORE INTO task_dependencies (predecessor_id, successor_id, dependency_type)
                VALUES (:pred, :succ, :dtype)
            """), {"pred": d[0], "succ": d[1], "dtype": d[2]})
        print(f"Inserted {len(all_deps)} task dependencies")

        # Also insert into task_dependencies_detail for lag_days support
        for d in all_deps:
            db.execute(text("""
                INSERT INTO task_dependencies_detail (predecessor_id, successor_id, dependency_type, lag_days, created_at)
                VALUES (:pred, :succ, :dtype, 0, :now)
            """), {"pred": d[0], "succ": d[1], "dtype": d[2], "now": now.isoformat()})

        # ========================================================
        # 3. PROJECT BASELINES (for Gantt baseline comparison)
        # ========================================================
        baselines = [
            (1, "Initial Baseline",  "Original project plan for Mobile App Redesign", now - timedelta(days=30), True, 1),
            (1, "Mid-Sprint Review", "Revised after sprint 2 retrospective",          now - timedelta(days=10), False, 1),
            (2, "Initial Baseline",  "Original plan for API Optimization",            now - timedelta(days=28), True, 1),
            (3, "Initial Baseline",  "Original plan for Database Migration",          now - timedelta(days=25), True, 1),
        ]
        for b in baselines:
            db.execute(text("""
                INSERT INTO project_baselines (project_id, name, description, baseline_date, is_active, created_by, created_at)
                VALUES (:pid, :name, :desc, :bdate, :active, :cby, :now)
            """), {"pid": b[0], "name": b[1], "desc": b[2], "bdate": b[3].isoformat(), "active": b[4], "cby": b[5], "now": now.isoformat()})
        print(f"Inserted {len(baselines)} project baselines")

        # Task baselines for project 1 initial baseline (baseline_id=1)
        bl_id = db.execute(text("SELECT id FROM project_baselines WHERE project_id=1 AND name='Initial Baseline'")).scalar()
        if bl_id:
            # Baseline snapshot of all project 1 tasks (original plan dates, slightly different from current)
            all_p1_task_ids = [1] + [t[0] for t in p1_tasks]
            for task_id in all_p1_task_ids:
                task = db.execute(text("SELECT id, title, created_at, due_date, estimated_hours, status, progress FROM tasks WHERE id=:tid"), {"tid": task_id}).fetchone()
                if task:
                    bl_start = datetime.fromisoformat(str(task[2])) - timedelta(days=3)  # baseline was 3 days earlier
                    bl_end = datetime.fromisoformat(str(task[3])) - timedelta(days=2) if task[3] else bl_start + timedelta(days=7)
                    db.execute(text("""
                        INSERT INTO task_baselines (baseline_id, task_id, baseline_start_date, baseline_end_date, baseline_duration, baseline_estimated_hours, baseline_status, baseline_progress)
                        VALUES (:bid, :tid, :bstart, :bend, :bdur, :bhrs, :bstatus, :bprog)
                    """), {
                        "bid": bl_id, "tid": task_id,
                        "bstart": bl_start.isoformat(), "bend": bl_end.isoformat(),
                        "bdur": max(1, (bl_end - bl_start).days),
                        "bhrs": task[4] if task[4] else 8.0,
                        "bstatus": "todo", "bprog": 0
                    })
            print(f"Inserted task baselines for project 1 baseline")

        # ========================================================
        # 4. BUDGET CATEGORIES
        # ========================================================
        categories = [
            ("Labor",         "LAB-001", "Personnel and contractor costs",    "labor"),
            ("Software",      "SW-001",  "Software licenses and tools",       "materials"),
            ("Hardware",      "HW-001",  "Hardware and infrastructure",       "materials"),
            ("Cloud Services","CLD-001", "Cloud hosting and services",        "services"),
            ("Consulting",    "CON-001", "External consulting fees",          "services"),
            ("Training",      "TRN-001", "Team training and certification",   "services"),
            ("Travel",        "TRV-001", "Travel and accommodation",          "other"),
            ("Contingency",   "CTG-001", "Risk contingency reserve",          "other"),
        ]
        for c in categories:
            db.execute(text("""
                INSERT INTO budget_categories (name, code, description, category_type, is_active, created_at)
                VALUES (:name, :code, :desc, :ctype, 1, :now)
            """), {"name": c[0], "code": c[1], "desc": c[2], "ctype": c[3], "now": now.isoformat()})
        print(f"Inserted {len(categories)} budget categories")

        # Get category IDs
        cat_ids = {}
        for row in db.execute(text("SELECT id, name FROM budget_categories")).fetchall():
            cat_ids[row[1]] = row[0]

        # ========================================================
        # 5. BUDGET ITEMS (for Projects 1, 2, 3, 5)
        # ========================================================
        budget_items = [
            # Project 1: Mobile App Redesign ($50,000 budget)
            (1, cat_ids["Labor"],          "UI/UX Design Team",          15000, 12500, 2000, "GL-5100", "CC-MOB", True,  "2026", "Q1", "approved"),
            (1, cat_ids["Labor"],          "Frontend Developers",        18000, 10800, 3000, "GL-5100", "CC-MOB", True,  "2026", "Q1", "approved"),
            (1, cat_ids["Software"],       "Design Tools (Figma, Sketch)", 2400, 2400, 0,   "GL-5200", "CC-MOB", False, "2026", "Q1", "spent"),
            (1, cat_ids["Cloud Services"], "Firebase & AWS Mobile",       5000, 1800, 1500, "GL-5300", "CC-MOB", True,  "2026", "Q1", "approved"),
            (1, cat_ids["Testing"],        "QA Testing Services",         4000, 0,    0,    "GL-5400", "CC-MOB", True,  "2026", "Q2", "planned") if "Testing" in cat_ids else None,
            (1, cat_ids["Contingency"],    "Project Contingency",         5600, 0,    0,    "GL-5900", "CC-MOB", False, "2026", "Q1", "planned"),

            # Project 2: Backend API Optimization ($30,000 budget)
            (2, cat_ids["Labor"],          "Senior Backend Developers",  16000, 14400, 0,   "GL-5100", "CC-API", True,  "2026", "Q1", "approved"),
            (2, cat_ids["Cloud Services"], "AWS Infrastructure Scale-up", 6000, 4200, 1000, "GL-5300", "CC-API", True,  "2026", "Q1", "approved"),
            (2, cat_ids["Software"],       "APM & Monitoring Tools",      3000, 3000, 0,    "GL-5200", "CC-API", False, "2026", "Q1", "spent"),
            (2, cat_ids["Consulting"],     "Performance Consultant",      5000, 4500, 0,    "GL-5500", "CC-API", True,  "2026", "Q1", "approved"),

            # Project 3: Database Migration ($25,000 budget)
            (3, cat_ids["Labor"],          "DBA Team",                   12000, 8400, 2000, "GL-5100", "CC-DBM", True,  "2026", "Q1", "approved"),
            (3, cat_ids["Cloud Services"], "Database Hosting (RDS)",      5000, 2500, 2000, "GL-5300", "CC-DBM", True,  "2026", "Q1", "approved"),
            (3, cat_ids["Consulting"],     "Migration Specialist",        4000, 3200, 0,    "GL-5500", "CC-DBM", True,  "2026", "Q1", "approved"),
            (3, cat_ids["Contingency"],    "Migration Risk Reserve",      4000, 500,  0,    "GL-5900", "CC-DBM", False, "2026", "Q1", "approved"),

            # Project 5: Security Audit ($40,000 budget)
            (5, cat_ids["Labor"],          "Security Engineers",         18000, 12000, 2000, "GL-5100", "CC-SEC", True,  "2026", "Q1", "approved"),
            (5, cat_ids["Consulting"],     "External Pen Testing Firm",  10000, 8000,  0,   "GL-5500", "CC-SEC", True,  "2026", "Q1", "approved"),
            (5, cat_ids["Software"],       "Security Scanning Tools",     4000, 4000,  0,   "GL-5200", "CC-SEC", False, "2026", "Q1", "spent"),
            (5, cat_ids["Training"],       "Security Training",           3000, 1200,  0,   "GL-5600", "CC-SEC", False, "2026", "Q1", "approved"),
            (5, cat_ids["Contingency"],    "Security Contingency",        5000, 0,     0,   "GL-5900", "CC-SEC", False, "2026", "Q1", "planned"),
        ]
        # Filter out None entries (in case a category didn't exist)
        budget_items = [b for b in budget_items if b is not None]

        for b in budget_items:
            variance = b[4] - b[3]  # actual - planned
            var_pct = (variance / b[3] * 100) if b[3] != 0 else 0
            db.execute(text("""
                INSERT INTO budget_items (project_id, category_id, description, planned_amount, actual_amount, committed_amount,
                    variance, variance_percentage, gl_code, cost_center, is_billable, fiscal_year, quarter, status, created_at)
                VALUES (:pid, :cid, :desc, :planned, :actual, :committed, :var, :var_pct, :gl, :cc, :bill, :fy, :q, :status, :now)
            """), {
                "pid": b[0], "cid": b[1], "desc": b[2], "planned": b[3], "actual": b[4], "committed": b[5],
                "var": variance, "var_pct": round(var_pct, 1), "gl": b[6], "cc": b[7], "bill": b[8],
                "fy": b[9], "q": b[10], "status": b[11], "now": now.isoformat()
            })
        print(f"Inserted {len(budget_items)} budget items")

        # ========================================================
        # 6. BUDGET TRANSACTIONS (Financial data)
        # ========================================================
        # Get budget item IDs
        bi_rows = db.execute(text("SELECT id, project_id, description FROM budget_items")).fetchall()
        bi_map = {(r[1], r[2]): r[0] for r in bi_rows}

        transactions = []
        # Project 1 transactions
        p1_labor_design = [k for k in bi_map if k[0] == 1 and "Design Team" in k[1]]
        p1_labor_dev = [k for k in bi_map if k[0] == 1 and "Frontend" in k[1]]
        p1_sw = [k for k in bi_map if k[0] == 1 and "Design Tools" in k[1]]
        p1_cloud = [k for k in bi_map if k[0] == 1 and "Firebase" in k[1]]

        if p1_labor_design:
            bid = bi_map[p1_labor_design[0]]
            transactions.extend([
                (bid, now - timedelta(days=28), "expense",    4500, "Jan sprint - UI design work",       "INV-2026-001", "InHouse Team",    "paid",    1, 1),
                (bid, now - timedelta(days=21), "expense",    4200, "Feb sprint - Wireframes & mockups", "INV-2026-012", "InHouse Team",    "paid",    1, 1),
                (bid, now - timedelta(days=14), "expense",    3800, "Mar sprint - Final designs",        "INV-2026-023", "InHouse Team",    "paid",    1, 1),
            ])
        if p1_labor_dev:
            bid = bi_map[p1_labor_dev[0]]
            transactions.extend([
                (bid, now - timedelta(days=25), "expense",    3600, "Sprint 1 - Navigation shell",      "INV-2026-005", "InHouse Dev",     "paid",    1, 1),
                (bid, now - timedelta(days=18), "expense",    3800, "Sprint 2 - Auth screens",          "INV-2026-015", "InHouse Dev",     "paid",    1, 1),
                (bid, now - timedelta(days=11), "expense",    3400, "Sprint 3 - API integration",       "INV-2026-025", "InHouse Dev",     "pending", 1, 1),
                (bid, now - timedelta(days=5),  "commitment", 3000, "Sprint 4 commitment - Push notifs","PO-2026-008",  "InHouse Dev",     "pending", 1, 1),
            ])
        if p1_sw:
            bid = bi_map[p1_sw[0]]
            transactions.extend([
                (bid, now - timedelta(days=30), "expense", 200, "Figma annual subscription (monthly)", "INV-2026-002", "Figma Inc",    "paid", 1, 1),
                (bid, now - timedelta(days=30), "expense", 2200, "Sketch team license",                "INV-2026-003", "Sketch BV",    "paid", 1, 1),
            ])
        if p1_cloud:
            bid = bi_map[p1_cloud[0]]
            transactions.extend([
                (bid, now - timedelta(days=20), "expense",    600,  "Firebase monthly - Jan",     "INV-2026-008", "Google Cloud", "paid",    1, 1),
                (bid, now - timedelta(days=10), "expense",    650,  "Firebase monthly - Feb",     "INV-2026-018", "Google Cloud", "paid",    1, 1),
                (bid, now - timedelta(days=3),  "expense",    550,  "AWS Mobile Hub - Mar",       "INV-2026-028", "AWS",          "pending", 1, 1),
                (bid, now,                      "commitment", 1500, "Q2 cloud services reserved", "PO-2026-010",  "Multi-cloud",  "pending", 1, 1),
            ])

        # Project 2 transactions
        p2_labor = [k for k in bi_map if k[0] == 2 and "Backend" in k[1]]
        p2_cloud = [k for k in bi_map if k[0] == 2 and "AWS" in k[1]]
        p2_consult = [k for k in bi_map if k[0] == 2 and "Consultant" in k[1]]
        p2_sw = [k for k in bi_map if k[0] == 2 and "Monitoring" in k[1]]

        if p2_labor:
            bid = bi_map[p2_labor[0]]
            transactions.extend([
                (bid, now - timedelta(days=26), "expense", 4800, "Sprint 1 - Endpoint profiling",  "INV-2026-004", "InHouse Dev",  "paid", 1, 1),
                (bid, now - timedelta(days=19), "expense", 5200, "Sprint 2 - Query optimization",  "INV-2026-014", "InHouse Dev",  "paid", 1, 1),
                (bid, now - timedelta(days=12), "expense", 4400, "Sprint 3 - Caching layer",       "INV-2026-024", "InHouse Dev",  "paid", 1, 1),
            ])
        if p2_cloud:
            bid = bi_map[p2_cloud[0]]
            transactions.extend([
                (bid, now - timedelta(days=22), "expense",    1400, "AWS EC2 scaling - Jan",          "INV-2026-007", "AWS",         "paid",    1, 1),
                (bid, now - timedelta(days=15), "expense",    1600, "AWS EC2 + ElastiCache - Feb",    "INV-2026-017", "AWS",         "paid",    1, 1),
                (bid, now - timedelta(days=8),  "expense",    1200, "AWS services - Mar",             "INV-2026-027", "AWS",         "pending", 1, 1),
                (bid, now,                      "commitment", 1000, "Q2 infra budget reserved",       "PO-2026-011",  "AWS",         "pending", 1, 1),
            ])
        if p2_consult:
            bid = bi_map[p2_consult[0]]
            transactions.extend([
                (bid, now - timedelta(days=20), "expense", 2500, "Performance audit - Phase 1",   "INV-2026-009", "PerfCo Ltd",  "paid",    1, 1),
                (bid, now - timedelta(days=8),  "expense", 2000, "Performance audit - Phase 2",   "INV-2026-019", "PerfCo Ltd",  "pending", 1, 1),
            ])
        if p2_sw:
            bid = bi_map[p2_sw[0]]
            transactions.extend([
                (bid, now - timedelta(days=28), "expense", 1500, "Datadog annual license",   "INV-2026-006", "Datadog Inc",  "paid", 1, 1),
                (bid, now - timedelta(days=28), "expense", 1500, "New Relic APM license",    "INV-2026-006b","New Relic",     "paid", 1, 1),
            ])

        # Project 3 transactions
        p3_labor = [k for k in bi_map if k[0] == 3 and "DBA" in k[1]]
        p3_cloud = [k for k in bi_map if k[0] == 3 and "RDS" in k[1]]
        p3_consult = [k for k in bi_map if k[0] == 3 and "Migration Specialist" in k[1]]

        if p3_labor:
            bid = bi_map[p3_labor[0]]
            transactions.extend([
                (bid, now - timedelta(days=24), "expense", 2800, "Schema audit work",         "INV-2026-010", "InHouse DBA", "paid",    1, 1),
                (bid, now - timedelta(days=17), "expense", 3200, "New schema design",         "INV-2026-020", "InHouse DBA", "paid",    1, 1),
                (bid, now - timedelta(days=10), "expense", 2400, "Migration script dev",      "INV-2026-030", "InHouse DBA", "pending", 1, 1),
            ])
        if p3_cloud:
            bid = bi_map[p3_cloud[0]]
            transactions.extend([
                (bid, now - timedelta(days=20), "expense",    1200, "RDS staging instance",   "INV-2026-011", "AWS",         "paid",    1, 1),
                (bid, now - timedelta(days=10), "expense",    1300, "RDS production prep",    "INV-2026-021", "AWS",         "pending", 1, 1),
                (bid, now,                      "commitment", 2000, "RDS prod reserved",      "PO-2026-012",  "AWS",         "pending", 1, 1),
            ])
        if p3_consult:
            bid = bi_map[p3_consult[0]]
            transactions.extend([
                (bid, now - timedelta(days=18), "expense", 1800, "Migration consulting P1",  "INV-2026-013", "DBExperts Co", "paid",    1, 1),
                (bid, now - timedelta(days=8),  "expense", 1400, "Migration consulting P2",  "INV-2026-022", "DBExperts Co", "pending", 1, 1),
            ])

        # Project 5 transactions
        p5_labor = [k for k in bi_map if k[0] == 5 and "Security Engineers" in k[1]]
        p5_consult = [k for k in bi_map if k[0] == 5 and "Pen Testing" in k[1]]
        p5_sw = [k for k in bi_map if k[0] == 5 and "Scanning Tools" in k[1]]
        p5_training = [k for k in bi_map if k[0] == 5 and "Training" in k[1]]

        if p5_labor:
            bid = bi_map[p5_labor[0]]
            transactions.extend([
                (bid, now - timedelta(days=22), "expense", 4000, "Vulnerability assessment",   "INV-2026-031", "InHouse Sec",  "paid",    1, 1),
                (bid, now - timedelta(days=15), "expense", 4500, "Pen test preparation",       "INV-2026-032", "InHouse Sec",  "paid",    1, 1),
                (bid, now - timedelta(days=8),  "expense", 3500, "Active pen testing",         "INV-2026-033", "InHouse Sec",  "pending", 1, 1),
            ])
        if p5_consult:
            bid = bi_map[p5_consult[0]]
            transactions.extend([
                (bid, now - timedelta(days=18), "expense", 5000, "External pen test - Phase 1", "INV-2026-034", "SecureTest LLC", "paid",    1, 1),
                (bid, now - timedelta(days=5),  "expense", 3000, "External pen test - Phase 2", "INV-2026-035", "SecureTest LLC", "pending", 1, 1),
            ])
        if p5_sw:
            bid = bi_map[p5_sw[0]]
            transactions.extend([
                (bid, now - timedelta(days=25), "expense", 2500, "Burp Suite Pro license",  "INV-2026-036", "PortSwigger", "paid", 1, 1),
                (bid, now - timedelta(days=25), "expense", 1500, "Nessus Pro license",      "INV-2026-037", "Tenable",     "paid", 1, 1),
            ])
        if p5_training:
            bid = bi_map[p5_training[0]]
            transactions.extend([
                (bid, now - timedelta(days=12), "expense", 1200, "OWASP security training",  "INV-2026-038", "SANS Institute", "paid", 1, 1),
            ])

        # Add some refund and adjustment transactions
        if p1_labor_design:
            bid = bi_map[p1_labor_design[0]]
            transactions.append(
                (bid, now - timedelta(days=7), "adjustment", -200, "Credit for tooling downtime", "ADJ-2026-001", "InHouse Team", "paid", 1, 1)
            )

        for t in transactions:
            db.execute(text("""
                INSERT INTO budget_transactions (budget_item_id, transaction_date, transaction_type, amount, description,
                    reference_number, vendor_name, payment_status, approved_by, created_by, created_at)
                VALUES (:bid, :tdate, :ttype, :amount, :desc, :ref, :vendor, :pstatus, :approver, :creator, :now)
            """), {
                "bid": t[0], "tdate": t[1].isoformat(), "ttype": t[2], "amount": t[3],
                "desc": t[4], "ref": t[5], "vendor": t[6], "pstatus": t[7],
                "approver": t[8], "creator": t[9], "now": now.isoformat()
            })
        print(f"Inserted {len(transactions)} budget transactions")

        # ========================================================
        # 7. CASH FLOW PROJECTIONS (Financial forecasting)
        # ========================================================
        cash_flows = []
        for pid, budget in [(1, 50000), (2, 30000), (3, 25000), (5, 40000)]:
            monthly_outflow_base = budget / 6  # ~6 month projects
            cumulative = 0
            for month_offset in range(-2, 5):  # 2 months ago to 4 months ahead
                period = now.replace(day=1) + timedelta(days=30 * month_offset)
                if month_offset < 0:
                    # Historical - actual values
                    outflow = monthly_outflow_base * (0.8 + 0.3 * abs(month_offset) / 2)
                    inflow = outflow * 0.1  # Small refunds/reimbursements
                    confidence = 100
                elif month_offset == 0:
                    outflow = monthly_outflow_base * 1.1
                    inflow = outflow * 0.05
                    confidence = 90
                else:
                    # Future - projected
                    outflow = monthly_outflow_base * (1.0 - 0.05 * month_offset)
                    inflow = outflow * 0.02
                    confidence = max(50, 85 - 8 * month_offset)

                net = inflow - outflow
                cumulative += net
                cash_flows.append((pid, period, round(inflow, 2), round(outflow, 2), round(net, 2), round(cumulative, 2), confidence))

        for cf in cash_flows:
            db.execute(text("""
                INSERT INTO cash_flow_projections (project_id, period, projected_inflow, projected_outflow, net_cash_flow, cumulative_cash_flow, confidence_level, created_at)
                VALUES (:pid, :period, :inflow, :outflow, :net, :cum, :conf, :now)
            """), {
                "pid": cf[0], "period": cf[1].isoformat(), "inflow": cf[2], "outflow": cf[3],
                "net": cf[4], "cum": cf[5], "conf": cf[6], "now": now.isoformat()
            })
        print(f"Inserted {len(cash_flows)} cash flow projections")

        # ========================================================
        # 8. KANBAN BOARDS & COLUMNS
        # ========================================================
        kanban_boards = [
            (1, "Mobile App Development Board", "Main Kanban board for Mobile App Redesign", True,  1),
            (2, "API Optimization Tracker",     "Sprint tracking for Backend API work",      True,  1),
            (3, "DB Migration Board",           "Database Migration tracking board",         True,  1),
            (5, "Security Audit Board",         "Security audit progress tracking",          True,  1),
        ]
        for kb in kanban_boards:
            db.execute(text("""
                INSERT INTO kanban_boards (project_id, name, description, is_default, created_by, created_at)
                VALUES (:pid, :name, :desc, :default, :cby, :now)
            """), {"pid": kb[0], "name": kb[1], "desc": kb[2], "default": kb[3], "cby": kb[4], "now": now.isoformat()})
        print(f"Inserted {len(kanban_boards)} kanban boards")

        # Get board IDs
        board_rows = db.execute(text("SELECT id, project_id FROM kanban_boards")).fetchall()
        board_map = {r[1]: r[0] for r in board_rows}

        # Columns for each board (4 standard columns + 1 extra)
        column_defs = [
            ("Backlog",     "#9e9e9e", 0, 0,  "todo",        False),
            ("In Progress", "#2196f3", 1, 5,  "in_progress", False),
            ("Review",      "#ff9800", 2, 3,  "review",      False),
            ("Testing",     "#9c27b0", 3, 3,  None,          False),
            ("Done",        "#4caf50", 4, 0,  "done",        True),
        ]
        for pid, board_id in board_map.items():
            for col in column_defs:
                db.execute(text("""
                    INSERT INTO kanban_columns (board_id, name, color, "order", wip_limit, task_status_mapping, is_done_column, created_at)
                    VALUES (:bid, :name, :color, :ord, :wip, :mapping, :done, :now)
                """), {
                    "bid": board_id, "name": col[0], "color": col[1], "ord": col[2],
                    "wip": col[3], "mapping": col[4], "done": col[5], "now": now.isoformat()
                })
        print(f"Inserted {len(column_defs) * len(board_map)} kanban columns")

        # ========================================================
        # 9. GANTT VIEWS (saved view configurations)
        # ========================================================
        gantt_views = [
            (1, "Timeline View",          "Default timeline view for Mobile App", "timeline", "day",   True,  True, True, True, "status",   True,  1),
            (1, "Resource View",          "Resource allocation view",             "resource", "week",  False, True, True, True, "assignee", False, 1),
            (2, "API Sprint Timeline",    "Sprint-level view",                   "timeline", "day",   True,  True, True, True, "priority", True,  1),
            (2, "Baseline Comparison",    "Compare current vs baseline",         "baseline", "week",  True,  True, True, True, "status",   False, 1),
            (3, "Migration Timeline",     "Database migration phases",           "timeline", "week",  True,  True, True, True, "status",   True,  1),
            (5, "Security Audit Timeline","Audit phases and milestones",         "timeline", "day",   True,  True, True, True, "priority", True,  1),
        ]
        for gv in gantt_views:
            db.execute(text("""
                INSERT INTO gantt_views (project_id, name, description, view_type, zoom_level,
                    show_critical_path, show_milestones, show_dependencies, show_progress,
                    color_by, is_default, created_by, created_at)
                VALUES (:pid, :name, :desc, :vtype, :zoom, :cp, :ms, :deps, :prog, :color, :default, :cby, :now)
            """), {
                "pid": gv[0], "name": gv[1], "desc": gv[2], "vtype": gv[3], "zoom": gv[4],
                "cp": gv[5], "ms": gv[6], "deps": gv[7], "prog": gv[8], "color": gv[9],
                "default": gv[10], "cby": gv[11], "now": now.isoformat()
            })
        print(f"Inserted {len(gantt_views)} gantt views")

        # ========================================================
        # 10. UPDATE PROJECT actual_cost and progress from budget data
        # ========================================================
        for pid in [1, 2, 3, 5]:
            total_actual = db.execute(text("SELECT COALESCE(SUM(actual_amount), 0) FROM budget_items WHERE project_id=:pid"), {"pid": pid}).scalar()
            task_count = db.execute(text("SELECT COUNT(*) FROM tasks WHERE project_id=:pid"), {"pid": pid}).scalar()
            if task_count > 0:
                avg_progress = db.execute(text("SELECT AVG(progress) FROM tasks WHERE project_id=:pid"), {"pid": pid}).scalar()
            else:
                avg_progress = 0
            db.execute(text("UPDATE projects SET actual_cost=:cost, progress=:prog WHERE id=:pid"),
                       {"cost": int(total_actual), "prog": int(avg_progress or 0), "pid": pid})
        print("Updated project actual_cost and progress")

        db.commit()
        print("\n=== SEED COMPLETE ===")

        # Print summary
        for table in ['tasks', 'task_dependencies', 'budget_categories', 'budget_items',
                       'budget_transactions', 'cash_flow_projections', 'kanban_boards',
                       'kanban_columns', 'gantt_views', 'project_baselines', 'task_baselines']:
            count = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"  {table}: {count} rows")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
