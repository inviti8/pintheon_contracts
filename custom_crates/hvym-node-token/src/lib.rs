#![no_std]

use crate::event::Events;
use crate::nodemetadata::NodeMetadata;
use soroban_sdk::Env;

pub mod event;
pub mod filemetadata;

#[derive(Clone)]
pub struct TokenUtils(Env);

impl TokenUtils {
    #[inline(always)]
    pub fn new(env: &Env) -> TokenUtils {
        TokenUtils(env.clone())
    }

    pub fn metadata(&self) -> NodeMetadata {
        NodeMetadata::new(&self.0)
    }

    pub fn events(&self) -> Events {
        Events::new(&self.0)
    }
}
