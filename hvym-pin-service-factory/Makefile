default: build

all: test

test: build
	cargo test

build:
	$(MAKE) -C ../hvym-pin-service || break;
	stellar contract build
	@ls -l target/wasm32-unknown-unknown/release/*.wasm

fmt:
	cargo fmt --all

clean:
	cargo clean
