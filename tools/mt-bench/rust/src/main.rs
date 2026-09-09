use serde_json::Value;
use std::time::Instant;
use serde::Deserialize;

fn work(f: &str) -> String {
    let d = std::env::var("MTBENCH_WORK").unwrap_or_else(|_| std::env::temp_dir().join("mt-bench").to_string_lossy().into());
    format!("{}/{}", d, f)
}

fn rss_mb() -> f64 {
    let s = std::fs::read_to_string("/proc/self/statm").unwrap();
    let pages: f64 = s.split_whitespace().nth(1).unwrap().parse().unwrap();
    pages * 4096.0 / 1048576.0
}

#[derive(Deserialize, Clone)]
struct Sgv { mills: f64, sgv: i32, delta: Option<f64>, #[allow(dead_code)] direction: Option<String> }
struct Col { mills: Vec<f64>, sgv: Vec<i32>, delta: Vec<f32>, dir: Vec<u8> }

fn main() {
    let mode = std::env::args().nth(1).unwrap_or_else(|| "time".into());
    let raw = std::fs::read(work("t.json")).unwrap();
    let sgvraw = std::fs::read(work("sgvs.json")).unwrap();
    let base = rss_mb();
    match mode.as_str() {
        "time" => {
            let iters = 50;
            let t0 = Instant::now();
            for _ in 0..iters { let v: Value = serde_json::from_slice(&raw).unwrap(); std::hint::black_box(&v); }
            println!("{:<52}{:.2} ms", "rust serde_json -> Value (whole tenant, untyped)", t0.elapsed().as_secs_f64()*1000.0/iters as f64);
            let t1 = Instant::now();
            for _ in 0..iters { let v: Vec<Sgv> = serde_json::from_slice(&sgvraw).unwrap(); std::hint::black_box(&v); }
            println!("{:<52}{:.2} ms", "rust serde_json -> typed structs (sgvs only)", t1.elapsed().as_secs_f64()*1000.0/iters as f64);
            let t2 = Instant::now();
            for _ in 0..iters {
                let v: Vec<Sgv> = serde_json::from_slice(&sgvraw).unwrap();
                let c = Col{ mills: v.iter().map(|x| x.mills).collect(), sgv: v.iter().map(|x| x.sgv).collect(),
                             delta: v.iter().map(|x| x.delta.unwrap_or(0.0) as f32).collect(), dir: v.iter().map(|_| 4u8).collect() };
                std::hint::black_box(&c);
            }
            println!("{:<52}{:.2} ms", "rust parse -> columnar (sgvs only)", t2.elapsed().as_secs_f64()*1000.0/iters as f64);
            println!("rust baseline RSS: {:.1} MB", base);
        }
        "mem-value" => { let mut h: Vec<Value> = Vec::new(); for _ in 0..200 { h.push(serde_json::from_slice(&sgvraw).unwrap()); }
            let d = rss_mb()-base; println!("{:<30}{:>7.1} MB => {:>6.1} KB/tenant", "rust serde_json::Value", d, d/200.0*1024.0); std::hint::black_box(&h); }
        "mem-typed" => { let mut h: Vec<Vec<Sgv>> = Vec::new(); for _ in 0..200 { h.push(serde_json::from_slice(&sgvraw).unwrap()); }
            let d = rss_mb()-base; println!("{:<30}{:>7.1} MB => {:>6.1} KB/tenant", "rust typed structs", d, d/200.0*1024.0); std::hint::black_box(&h); }
        "mem-col" => { let mut h: Vec<Col> = Vec::new();
            for _ in 0..200 { let v: Vec<Sgv> = serde_json::from_slice(&sgvraw).unwrap();
                h.push(Col{ mills: v.iter().map(|x| x.mills).collect(), sgv: v.iter().map(|x| x.sgv).collect(),
                            delta: v.iter().map(|x| x.delta.unwrap_or(0.0) as f32).collect(), dir: v.iter().map(|_| 4u8).collect() }); }
            let d = rss_mb()-base; println!("{:<30}{:>7.1} MB => {:>6.1} KB/tenant", "rust columnar (SoA)", d, d/200.0*1024.0); std::hint::black_box(&h); }
        _ => {}
    }
}
