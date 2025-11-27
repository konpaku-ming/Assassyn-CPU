use crate::simulator::Simulator;
use sim_runtime::num_bigint::{BigInt, BigUint};
use sim_runtime::*;
use std::ffi::c_void;

// Elaborating module Driver
pub fn Driver(sim: &mut Simulator) -> bool {
  let cnt_rd = { sim.cnt.payload[false as usize].clone() };
  let v = { ValueCastTo::<u32>::cast(&cnt_rd) + ValueCastTo::<u32>::cast(&1u32) };
  // @/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:82
  {
    let stamp = sim.stamp - sim.stamp % 100 + 50;
    let write = ArrayWrite::new(stamp, false as usize, v.clone(), "Driver");
    sim.cnt.write(0, write);
  };
  let cnt_rd_1 = { sim.cnt.payload[false as usize].clone() };
  // @/home/tomorrow_arc1/CS/assassyn/MyCPU/main.py:85
  print!("@line:{:<5} {:<10}: [Driver]\t", line!(), cyclize(sim.stamp));
  println!("cnt: {}", cnt_rd_1,);

  true
}
