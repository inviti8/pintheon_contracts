#![no_std]

// Core token implementation
mod token;

// Custom metadata implementation
mod metadata;

// Re-export the token implementation
pub use token::{Token, TokenClient};

// Re-export the metadata interface
pub use metadata::NodeTokenInterface;
