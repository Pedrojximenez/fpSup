//! Serves a synthesised HFS+ volume over HTTP (Range requests) so macOS can attach it:
//!   diskutil image attach --readOnly http://127.0.0.1:PORT/volume.img
//!
//! usage: cdng-mount test PORT DIRS FILES_PER_DIR FILE_SIZE MANIFEST
//! Test mode: file contents are a pattern of (CNID, offset); MANIFEST lists every
//! file's path, CNID and size for verification after mounting.
use anyhow::{Context, Result, bail, ensure};
use std::{
    io::{BufRead, BufReader, Write},
    net::{TcpListener, TcpStream},
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

#[path = "../../cdng-image/rust/src/hfs.rs"]
mod hfs;

/// Test content: depends only on the file's CNID and the byte offset.
pub fn pattern(cnid: u32, off: u64, out: &mut [u8]) {
    for (i, b) in out.iter_mut().enumerate() {
        let x = (off + i as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15) ^ (cnid as u64).wrapping_mul(0xC2B2_AE3D_27D4_EB4F);
        *b = (x >> 56) as u8;
    }
}

fn serve(stream: TcpStream, vol: Arc<hfs::Volume>, stats: Arc<std::sync::Mutex<(u64, u64)>>) -> Result<()> {
    let mut reader = BufReader::new(stream.try_clone()?);
    let mut writer = stream;
    loop {
        let mut line = String::new();
        if reader.read_line(&mut line)? == 0 {
            return Ok(());
        }
        let method = line.split_whitespace().next().unwrap_or("").to_string();
        let mut range = None;
        loop {
            let mut h = String::new();
            reader.read_line(&mut h)?;
            let h = h.trim_end();
            if h.is_empty() {
                break;
            }
            if let Some(v) = h.strip_prefix("Range: bytes=").or_else(|| h.strip_prefix("range: bytes=")) {
                let (a, b) = v.split_once('-').context("bad range")?;
                let a: u64 = a.parse()?;
                let b: u64 = if b.is_empty() { vol.bytes - 1 } else { b.parse()? };
                range = Some((a, b.min(vol.bytes - 1)));
            }
        }
        match (method.as_str(), range) {
            ("HEAD", _) => write!(
                writer,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nAccept-Ranges: bytes\r\nContent-Type: application/octet-stream\r\n\r\n",
                vol.bytes
            )?,
            ("GET", Some((a, b))) => {
                ensure!(a <= b, "empty range");
                let mut buf = vec![0u8; (b - a + 1) as usize];
                vol.read(a, &mut buf, &|f, off, out| pattern(f.cnid, off, out));
                {
                    let mut s = stats.lock().unwrap();
                    s.0 += 1;
                    s.1 += buf.len() as u64;
                }
                write!(
                    writer,
                    "HTTP/1.1 206 Partial Content\r\nContent-Length: {}\r\nContent-Range: bytes {a}-{b}/{}\r\nAccept-Ranges: bytes\r\nContent-Type: application/octet-stream\r\n\r\n",
                    buf.len(),
                    vol.bytes
                )?;
                writer.write_all(&buf)?;
            }
            _ => bail!("unsupported request {line:?}"),
        }
        writer.flush()?;
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    ensure!(args.len() == 7 && args[1] == "test", "usage: cdng-mount test PORT DIRS FILES_PER_DIR FILE_SIZE MANIFEST");
    let port: u16 = args[2].parse()?;
    let (ndirs, nfiles, size): (usize, usize, u64) = (args[3].parse()?, args[4].parse()?, args[5].parse()?);
    let dirs: Vec<hfs::Dir> = (0..ndirs).map(|d| hfs::Dir { name: format!("A001_{:03}", d + 1), parent: None }).collect();
    let files: Vec<hfs::File> = (0..ndirs)
        .flat_map(|d| {
            (0..nfiles).map(move |f| hfs::File {
                dir: Some(d),
                name: format!("A001_{:03}_20261024_{:06}.DNG", d + 1, f + 1),
                // vary sizes a little so files do not all end on the same block boundary
                size: size + (f as u64 % 7) * 1000,
            })
        })
        .collect();
    let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs() + 2_082_844_800; // 1904 epoch
    let t = std::time::Instant::now();
    let vol = Arc::new(hfs::Volume::build("CDNG", &dirs, &files, now as u32)?);
    println!(
        "volume: {} dirs, {} files, {:.1} GB virtual, built in {:.0} ms",
        ndirs,
        vol.files.len(),
        vol.bytes as f64 / 1e9,
        t.elapsed().as_secs_f64() * 1e3
    );
    let mut m = String::new();
    for (f, src) in vol.files.iter().zip(&files) {
        m += &format!("{}/{}\t{}\t{}\n", dirs[src.dir.unwrap()].name, src.name, f.cnid, f.size);
    }
    std::fs::write(&args[6], m)?;

    let stats = Arc::new(std::sync::Mutex::new((0u64, 0u64)));
    let listener = TcpListener::bind(("127.0.0.1", port))?;
    println!("serving http://127.0.0.1:{port}/volume.img");
    {
        let stats = stats.clone();
        std::thread::spawn(move || loop {
            std::thread::sleep(std::time::Duration::from_secs(5));
            let s = stats.lock().unwrap();
            eprintln!("requests {} bytes {}", s.0, s.1);
        });
    }
    for s in listener.incoming() {
        let (s, vol, stats) = (s?, vol.clone(), stats.clone());
        std::thread::spawn(move || {
            if let Err(e) = serve(s, vol, stats) {
                eprintln!("connection: {e:#}");
            }
        });
    }
    Ok(())
}
