"""Build a recipient-replaceable _imagingft without altering installed files."""
import argparse,hashlib,json,os,subprocess,tarfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--python-prefix',required=True);p.add_argument('--pillow-libs',required=True);p.add_argument('--archives',required=True);p.add_argument('--output',required=True);p.add_argument('--pillow-source',help='Optional recipient-modified extracted Pillow source tree');args=p.parse_args()
prefix=Path(args.python_prefix).resolve();libs=Path(args.pillow_libs).resolve();archives=Path(args.archives).resolve();out=Path(args.output).resolve()
out.mkdir(parents=True,exist_ok=False)
for name in ('pillow-12.3.0.tar.gz','freetype-2.14.3.tar.gz','harfbuzz-14.2.1.tar.xz'):
    with tarfile.open(archives/name) as t:t.extractall(out,filter='data')
src=(Path(args.pillow_source).resolve() if args.pillow_source else out/'pillow-12.3.0')/'src';target=out/'_imagingft.cpython-312-x86_64-linux-gnu.so'
ft=next(libs.glob('libfreetype-*.so.*'));hb=next(libs.glob('libharfbuzz-*.so.*'))
cmd=['gcc','-shared','-fPIC','-O2','-DHAVE_RAQM','-I'+str(prefix/'include/python3.12'),'-I'+str(src),'-I'+str(out/'freetype-2.14.3/include'),'-I'+str(out/'harfbuzz-14.2.1/src'),str(src/'_imagingft.c'),str(src/'libImaging/Mode.c'),str(src/'thirdparty/raqm/raqm.c'),str(src/'thirdparty/fribidi-shim/fribidi.c'),'-L'+str(libs),'-l:'+ft.name,'-l:'+hb.name,'-Wl,-rpath,'+str(libs),'-ldl','-o',str(target)]
r=subprocess.run(cmd,text=True,capture_output=True)
record={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'original_install_unchanged':True,'source_sha256':{x:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in cmd if x.endswith('.c')}}
record['compiler']=subprocess.run(['gcc','--version'],text=True,capture_output=True,check=True).stdout
record['link_inputs']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (prefix/'bin/python3.12',ft,hb)}
if r.returncode==0:
    record['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    # Load this output explicitly; do not silently import the original module.
    probe="import importlib.util,json; s=importlib.util.spec_from_file_location('_imagingft',"+repr(str(target))+");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps({'file':m.__file__,'freetype':m.freetype2_version,'raqm':m.raqm_version,'harfbuzz':m.harfbuzz_version}))"
    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(libs)
    test=subprocess.run([str(prefix/'bin/python3.12'),'-I','-B','-c',probe],env=env,text=True,capture_output=True)
    record['load_test']={'returncode':test.returncode,'stdout':test.stdout,'stderr':test.stderr}
(out/'relink-proof.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2));raise SystemExit(r.returncode or record['load_test']['returncode'])
