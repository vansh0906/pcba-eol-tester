//! tlog: production test-log analytics.
//!
//! Reads the tester's CSV log (one row per test per unit, in test order) and prints a JSON summary:
//! units, first-pass yield, yield per station, first-fail Pareto and, for every parametric test, the mean,
//! standard deviation and Cpk on units that passed. Standard library only, so it builds anywhere.
//!
//!     cargo run --release -- ../../results/pilot_log.csv
use std::collections::BTreeMap;
use std::env;
use std::fs;
use std::process::ExitCode;

#[derive(Debug, Clone)]
pub struct Row {
    pub serial: String,
    pub station: String,
    pub test: String,
    pub name: String,
    pub value: Option<f64>,
    pub lo: Option<f64>,
    pub hi: Option<f64>,
    pub pass: bool,
}

pub fn parse(text: &str) -> Result<Vec<Row>, String> {
    let mut lines = text.lines();
    let header: Vec<&str> = lines.next().ok_or("empty file")?.split(',').collect();
    let col = |n: &str| {
        header
            .iter()
            .position(|h| *h == n)
            .ok_or(format!("missing column {n}"))
    };
    let (cs, cst, ct, cn, cv, cl, ch, cp) = (
        col("serial")?,
        col("station")?,
        col("test")?,
        col("name")?,
        col("value")?,
        col("lo")?,
        col("hi")?,
        col("pass")?,
    );
    let num = |s: &str| {
        if s.is_empty() {
            None
        } else {
            s.parse::<f64>().ok()
        }
    };
    let mut rows = Vec::new();
    for (i, line) in lines.enumerate() {
        if line.trim().is_empty() {
            continue;
        }
        let f: Vec<&str> = line.split(',').collect();
        if f.len() < header.len() {
            return Err(format!(
                "line {}: {} fields, expected {}",
                i + 2,
                f.len(),
                header.len()
            ));
        }
        rows.push(Row {
            serial: f[cs].to_string(),
            station: f[cst].to_string(),
            test: f[ct].to_string(),
            name: f[cn].to_string(),
            value: num(f[cv]),
            lo: num(f[cl]),
            hi: num(f[ch]),
            pass: f[cp] == "1",
        });
    }
    Ok(rows)
}

/// Mean, sample standard deviation and Cpk against [lo, hi].
pub fn cpk(v: &[f64], lo: f64, hi: f64) -> (f64, f64, f64) {
    let n = v.len() as f64;
    let m = v.iter().sum::<f64>() / n;
    let sd = (v.iter().map(|x| (x - m).powi(2)).sum::<f64>() / (n - 1.0)).sqrt();
    let c = if sd > 0.0 {
        (hi - m).min(m - lo) / (3.0 * sd)
    } else {
        f64::INFINITY
    };
    (m, sd, c)
}

pub struct Summary {
    pub units: usize,
    pub passed: usize,
    pub station: BTreeMap<String, (usize, usize)>,
    pub pareto: Vec<(String, usize)>,
    pub tests: Vec<(String, String, usize, f64, f64, f64)>,
}

pub fn summarize(rows: &[Row]) -> Summary {
    // unit -> (station, passed, first failing test), keeping first-seen order
    let mut order: Vec<String> = Vec::new();
    let mut unit: BTreeMap<String, (String, bool, Option<String>)> = BTreeMap::new();
    for r in rows {
        let e = unit.entry(r.serial.clone()).or_insert_with(|| {
            order.push(r.serial.clone());
            (r.station.clone(), true, None)
        });
        if !r.pass {
            if e.2.is_none() {
                e.2 = Some(r.test.clone());
            }
            e.1 = false;
        }
    }
    let passed = unit.values().filter(|u| u.1).count();
    let mut station: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    let mut pareto: BTreeMap<String, usize> = BTreeMap::new();
    for s in &order {
        let u = &unit[s];
        let e = station.entry(u.0.clone()).or_insert((0, 0));
        e.0 += 1;
        if u.1 {
            e.1 += 1;
        }
        if let Some(t) = &u.2 {
            *pareto.entry(t.clone()).or_insert(0) += 1;
        }
    }
    let mut pareto: Vec<(String, usize)> = pareto.into_iter().collect();
    pareto.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));

    let mut vals: BTreeMap<String, (String, f64, f64, Vec<f64>)> = BTreeMap::new();
    for r in rows {
        if let (Some(v), Some(lo), Some(hi)) = (r.value, r.lo, r.hi) {
            if unit[&r.serial].1 {
                vals.entry(r.test.clone())
                    .or_insert((r.name.clone(), lo, hi, Vec::new()))
                    .3
                    .push(v);
            }
        }
    }
    let tests = vals
        .into_iter()
        .filter(|(_, v)| v.3.len() > 1)
        .map(|(t, (name, lo, hi, v))| {
            let (m, sd, c) = cpk(&v, lo, hi);
            (t, name, v.len(), m, sd, c)
        })
        .collect();
    Summary {
        units: unit.len(),
        passed,
        station,
        pareto,
        tests,
    }
}

fn json(s: &Summary) -> String {
    let mut o = String::from("{\n");
    o += &format!("  \"units\": {},\n  \"passed\": {},\n", s.units, s.passed);
    o += &format!(
        "  \"fpy_pct\": {:.4},\n",
        100.0 * s.passed as f64 / s.units.max(1) as f64
    );
    let st: Vec<String> = s
        .station
        .iter()
        .map(|(k, (n, p))| {
            format!(
                "\"{k}\": {{\"units\": {n}, \"passed\": {p}, \"yield_pct\": {:.4}}}",
                100.0 * *p as f64 / *n as f64
            )
        })
        .collect();
    o += &format!("  \"stations\": {{{}}},\n", st.join(", "));
    let pa: Vec<String> = s
        .pareto
        .iter()
        .map(|(t, n)| format!("\"{t}\": {n}"))
        .collect();
    o += &format!("  \"pareto_first_fail\": {{{}}},\n", pa.join(", "));
    let te: Vec<String> = s
        .tests
        .iter()
        .map(|(t, name, n, m, sd, c)| {
            format!("    \"{t}\": {{\"name\": \"{name}\", \"n\": {n}, \"mean\": {m:.9e}, \"sd\": {sd:.9e}, \"cpk\": {c:.6}}}")
        })
        .collect();
    o += &format!("  \"tests\": {{\n{}\n  }}\n}}", te.join(",\n"));
    o
}

fn main() -> ExitCode {
    let path = match env::args().nth(1) {
        Some(p) => p,
        None => {
            eprintln!("usage: tlog <tester_log.csv>");
            return ExitCode::from(2);
        }
    };
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("tlog: {path}: {e}");
            return ExitCode::from(1);
        }
    };
    match parse(&text) {
        Ok(rows) => {
            println!("{}", json(&summarize(&rows)));
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("tlog: {e}");
            ExitCode::from(1)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const LOG: &str = "serial,station,rev,test,name,value,lo,hi,pass,time_s
U1,ST1,B,T01,a,1.0,0,2,1,0.1
U1,ST1,B,T02,b,ok,,,1,0.1
U2,ST2,B,T01,a,3.0,0,2,0,0.1
U2,ST2,B,T02,b,no-ack,,,0,0.1
U3,ST1,B,T01,a,1.2,0,2,1,0.1
U3,ST1,B,T02,b,no-ack,,,0,0.1
U4,ST2,B,T01,a,0.8,0,2,1,0.1
U4,ST2,B,T02,b,ok,,,1,0.1
";

    #[test]
    fn yield_pareto_and_stations() {
        let s = summarize(&parse(LOG).unwrap());
        assert_eq!((s.units, s.passed), (4, 2));
        assert_eq!(
            s.pareto,
            vec![("T01".to_string(), 1), ("T02".to_string(), 1)]
        );
        assert_eq!(s.station["ST1"], (2, 1));
        assert_eq!(s.station["ST2"], (2, 1));
    }

    #[test]
    fn cpk_uses_only_passing_units() {
        let s = summarize(&parse(LOG).unwrap());
        let t = &s.tests[0];
        assert_eq!(t.2, 2); // U1 and U4 passed; U2 and U3 did not
        assert!((t.3 - 0.9).abs() < 1e-12);
        let (_, sd, c) = cpk(&[1.0, 0.8], 0.0, 2.0);
        assert!((sd - 0.1414213562).abs() < 1e-9);
        assert!((c - 0.9 / (3.0 * sd)).abs() < 1e-9);
    }

    #[test]
    fn rejects_short_lines() {
        assert!(parse("serial,station,rev,test,name,value,lo,hi,pass,time_s\nU1,ST1\n").is_err());
    }
}
