//! Decode the QR that the installed `vadgr pair` actually printed.
//!
//! The runbook's `G3` oracle. It reads the rendered half-block symbol from a
//! file, rebuilds the module matrix from it, and hands that to `rqrr`, which is
//! a different implementation from the encoder the product uses. What comes back
//! is compared with the deep link rebuilt from the fields the CLI printed beside
//! the symbol, so nothing in this check trusts the encoder under test.

use std::io::Read;

fn main() {
    let mut args = std::env::args().skip(1);
    let path = args.next().expect("usage: decode_render <render-file> <expected-uri>");
    let expected = args.next().expect("usage: decode_render <render-file> <expected-uri>");

    let mut text = String::new();
    std::fs::File::open(&path)
        .expect("the render file opens")
        .read_to_string(&mut text)
        .expect("the render file reads");

    // Keep only the drawn lines: every character is one of the four half blocks.
    let lines: Vec<&str> = text
        .lines()
        .filter(|l| !l.is_empty() && l.chars().all(|c| matches!(c, '\u{2588}' | '\u{2580}' | '\u{2584}' | ' ')))
        .collect();
    assert!(!lines.is_empty(), "no rendered symbol found in {path}");
    let width = lines[0].chars().count();
    let height = lines.len() * 2;
    println!("render: {width} columns x {} printed lines ({height} module rows)", lines.len());

    // The CLI draws the dark-terminal form, so a printed block is a LIGHT module.
    let mut dark = vec![vec![false; width]; height];
    for (row, line) in lines.iter().enumerate() {
        for (col, c) in line.chars().enumerate() {
            let (top, bottom) = match c {
                '\u{2588}' => (true, true),
                '\u{2580}' => (true, false),
                '\u{2584}' => (false, true),
                _ => (false, false),
            };
            dark[row * 2][col] = !top;
            dark[row * 2 + 1][col] = !bottom;
        }
    }

    // Scale to pixels so a detector has something to find.
    const SCALE: u32 = 8;
    let mut img = image::GrayImage::new(width as u32 * SCALE, height as u32 * SCALE);
    for (y, row) in dark.iter().enumerate() {
        for (x, module) in row.iter().enumerate() {
            let value = if *module { 0u8 } else { 255u8 };
            for dy in 0..SCALE {
                for dx in 0..SCALE {
                    img.put_pixel(x as u32 * SCALE + dx, y as u32 * SCALE + dy, image::Luma([value]));
                }
            }
        }
    }

    let mut prepared = rqrr::PreparedImage::prepare(img);
    let grids = prepared.detect_grids();
    println!("grids detected: {}", grids.len());
    assert_eq!(grids.len(), 1, "exactly one symbol must be found on the screen");
    let (meta, decoded) = grids[0].decode().expect("the printed symbol decodes");
    println!("version: {:?}  ecc level: {}", meta.version, meta.ecc_level);
    println!("decoded: {decoded}");
    println!("expected: {expected}");
    assert_eq!(decoded, expected, "the symbol on the screen is not the link the phone needs");
    println!("MATCH: the QR on the screen carries exactly the deep link the CLI printed beside it");
}
