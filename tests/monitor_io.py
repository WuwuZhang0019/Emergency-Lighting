"""UTF-8 ADODB adapter; Date: 2026-10-13. No native CAD acceptance."""
from pathlib import Path

def install_monitor_io(host):
    streams = []
    def create(name):
        assert name == 'ADODB.Stream'
        stream = {'closed': False, 'released': False}
        streams.append(stream)
        return stream
    def invoke(stream, method, *args):
        method = str(method).upper()
        if method == 'OPEN':
            assert args == (None, 0, -1, '', '')
        elif method == 'WRITETEXT':
            assert args[1] == 0
            stream['text'] = args[0]
        elif method == 'SAVETOFILE':
            assert args[1] == 1
            assert stream['CHARSET'] == 'utf-8' and stream['TYPE'] == 2
            with open(args[0], 'xb') as file:
                file.write(stream['text'].encode('utf-8-sig'))
        elif method == 'CLOSE':
            stream['closed'] = True
        else:
            raise AssertionError(method)
    host.builtins.update({
        'VLAX-CREATE-OBJECT': create,
        'VLAX-PUT-PROPERTY': lambda stream, key, value: stream.__setitem__(str(key), value),
        'VLAX-INVOKE-METHOD': invoke,
        'VLAX-RELEASE-OBJECT': lambda stream: stream.__setitem__('released', True),
        'VL-FILE-DELETE': lambda path: Path(path).unlink(missing_ok=True) or True,
        'VL-FILE-RENAME': lambda src, dst: Path(src).rename(dst) or True,
    })
    return streams
