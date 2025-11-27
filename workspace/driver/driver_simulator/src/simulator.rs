use crate::modules;
use sim_runtime::num_bigint::{BigInt, BigUint};
use sim_runtime::rand::seq::SliceRandom;
use sim_runtime::*;
use std::collections::HashMap;
use std::collections::VecDeque;
use std::sync::Arc;

pub struct Simulator {
  pub stamp: usize,
  pub request_stamp_map_table: HashMap<i64, usize>,
  pub cnt: Array<u32>,
  pub Driver_triggered: bool,
  pub Driver_event: VecDeque<usize>,
}

impl Simulator {
  pub fn new() -> Self {
    Simulator {
      stamp: 0,
      request_stamp_map_table: HashMap::new(),
      cnt: Array::new_with_ports(1, 1),
      Driver_triggered: false,
      Driver_event: VecDeque::new(),
    }
  }

  fn event_valid(&self, event: &VecDeque<usize>) -> bool {
    event.front().map_or(false, |x| *x <= self.stamp)
  }

  pub fn reset_downstream(&mut self) {
    self.Driver_triggered = false;
  }

  pub fn tick_registers(&mut self) {
    self.cnt.tick(self.stamp);
  }

  pub fn reset_dram(&mut self) {}

  fn simulate_Driver(&mut self) {
    if self.event_valid(&self.Driver_event) {
      let succ = modules::Driver::Driver(self);
      if succ {
        self.Driver_event.pop_front();
      } else {
      }
      self.Driver_triggered = succ;
    } // close event condition
  } // close function
}

pub fn simulate() {
  let mut sim = Simulator::new();
  let simulators: Vec<fn(&mut Simulator)> = vec![Simulator::simulate_Driver];
  let downstreams: Vec<fn(&mut Simulator)> = vec![];

  for i in 1..=100 {
    sim.Driver_event.push_back(i * 100);
  }
  let mut idle_count = 0;
  for i in 1..=100 {
    sim.stamp = i * 100;
    sim.reset_downstream();

    for simulate in simulators.iter() {
      simulate(&mut sim);
    }

    for simulate in downstreams.iter() {
      simulate(&mut sim);
    }

    let any_module_triggered = sim.Driver_triggered;

    // Handle idle threshold
    if !any_module_triggered {
      idle_count += 1;
      if idle_count >= 100 {
        println!("Simulation stopped due to reaching idle threshold of 100");
        break;
      }
    } else {
      idle_count = 0;
    }

    sim.stamp += 50;
    sim.tick_registers();
    sim.reset_dram();
    unsafe {
      // Tick all DRAM memory interfaces
    }
  }
}
