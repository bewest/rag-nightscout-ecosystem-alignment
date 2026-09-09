Rust counterpart to the Node micro-benchmarks, answering "would a non-Node host help?".

Fixtures are shared with the Node scripts. Generate them first:

    node -e "const {mkTenant}=require('../gen');const fs=require('fs');const os=require('os');
      const d=process.env.MTBENCH_WORK||os.tmpdir()+'/mt-bench';fs.mkdirSync(d,{recursive:true});
      const t=mkTenant();fs.writeFileSync(d+'/t.json',JSON.stringify(t));
      fs.writeFileSync(d+'/sgvs.json',JSON.stringify(t.sgvs));"

Then:

    cargo run --release -- time        # parse throughput, three representations
    cargo run --release -- mem-value   # RSS for 200 tenants, serde_json::Value
    cargo run --release -- mem-typed   # RSS for 200 tenants, typed structs
    cargo run --release -- mem-col     # RSS for 200 tenants, columnar struct-of-arrays

Memory modes run one representation per process on purpose: the allocator reuses freed
pages, so measuring several shapes in one process understates the later ones badly.

Dependency versions are pinned low because the machine used had rustc 1.68. On a modern
toolchain, drop the `=` pins in Cargo.toml.
