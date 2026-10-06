#!/usr/bin/env python3
# adb_swiss.py — canivete suico do adb / adb swiss army knife
# stdlib pura (python >= 3.8). Menu interativo ou comando unico.
import datetime, os, re, shutil, subprocess, sys, time

VERSAO = "1.0"
OUT_RAIZ = "adb-swiss-out"

COMANDOS = ["info", "foto", "grava", "backup", "puxa", "instala", "desinstala",
            "espelha", "dispositivos", "ajuda", "menu"]


def monta_env(adbroot):
    env = os.environ.copy()
    if adbroot and os.path.isdir(adbroot):
        env["PATH"] = os.pathsep.join([os.path.join(adbroot, "usr", "bin"), env.get("PATH", "")])
        libs = [os.path.join(adbroot, "usr", "lib", "x86_64-linux-gnu", "android"),
                os.path.join(adbroot, "usr", "lib", "x86_64-linux-gnu"),
                os.path.join(adbroot, "lib", "x86_64-linux-gnu")]
        env["LD_LIBRARY_PATH"] = os.pathsep.join(libs + [env.get("LD_LIBRARY_PATH", "")])
    return env


def achar_adb(env):
    return shutil.which("adb", path=env.get("PATH"))


def run_adb(env, args, timeout=120):
    cmd = ["adb"] + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", "timeout apos %ds" % timeout


def dispositivos(env):
    rc, out, err = run_adb(env, ["devices"])
    lista = []
    for linha in out.splitlines()[1:]:
        m = re.match(r"^(\S+)\s+(\S+)", linha.strip())
        if m:
            lista.append((m.group(1), m.group(2)))
    return lista


def exige_device(env, serial):
    lista = dispositivos(env)
    if not lista:
        erro("nenhum dispositivo conectado. habilite USB debugging no aparelho e confira 'adb devices'.")
    ativos = [s for (s, st) in lista if st == "device"]
    if serial:
        if serial not in [s for (s, _) in lista]:
            erro("serial '%s' nao esta entre os dispositivos visiveis." % serial)
        return serial
    if len(ativos) == 1:
        return ativos[0]
    if not ativos:
        erro("dispositivos presentes mas nenhum autorizado: %s" % ", ".join("%s[%s]" % x for x in lista))
    erro("multiplos dispositivos (%s). use -s SERIAL ou ANDROID_SERIAL." % ", ".join(ativos))


def erro(msg):
    print("ERRO: " + msg)
    sys.exit(1)


def alvo(serial):
    return ["-s", serial] if serial else []


def getprop(env, serial, chave):
    rc, out, _ = run_adb(env, alvo(serial) + ["shell", "getprop", chave])
    return out.strip() if rc == 0 else ""


def pasta_saida():
    nome = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    p = os.path.join(OUT_RAIZ, nome)
    os.makedirs(p, exist_ok=True)
    return p


def log_ok(pasta, msg):
    with open(os.path.join(pasta, "operacoes.log"), "a") as f:
        f.write("[%s] %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg))


def cmd_info(env, serial, _resto):
    serial = exige_device(env, serial)
    print("dispositivo : %s" % serial)
    campos = [("fabricante", "ro.product.manufacturer"), ("modelo", "ro.product.model"),
              ("android", "ro.build.version.release"), ("sdk", "ro.build.version.sdk"),
              ("patch seguranca", "ro.build.version.security_patch"),
              ("build", "ro.build.display.id")]
    for rotulo, chave in campos:
        print("%-16s: %s" % (rotulo, getprop(env, serial, chave) or "?"))
    rc, out, _ = run_adb(env, alvo(serial) + ["shell", "dumpsys", "battery"])
    nivel = re.search(r"level:\s*(\d+)", out)
    status = re.search(r"status:\s*(\d+)", out)
    if nivel:
        st = {1: "desconhecido", 2: "carregando", 3: "descarregando", 4: "cheia", 5: "sem bateria"}.get(
            int(status.group(1)) if status else 0, "?")
        print("%-16s: %s%% (%s)" % ("bateria", nivel.group(1), st))
    rc, out, _ = run_adb(env, alvo(serial) + ["shell", "wm", "size"])
    print("%-16s: %s" % ("tela", out.strip()))
    rc, out, _ = run_adb(env, alvo(serial) + ["shell", "wm", "density"])
    print("%-16s: %s" % ("densidade", out.strip()))
    return 0


def cmd_dispositivos(env, _serial, _resto):
    lista = dispositivos(env)
    if not lista:
        print("nenhum dispositivo. conecte um aparelho com USB debugging ativa.")
        return 0
    for s, st in lista:
        print("%s [%s]" % (s, st))
    return 0


def cmd_foto(env, serial, _resto):
    serial = exige_device(env, serial)
    pasta = pasta_saida()
    remoto = "/sdcard/adb-swiss-%d.png" % int(time.time())
    rc, _, err = run_adb(env, alvo(serial) + ["shell", "screencap", "-p", remoto])
    if rc != 0:
        erro("screencap falhou no device: %s" % err.strip())
    local = os.path.join(pasta, "screenshot.png")
    rc, _, err = run_adb(env, alvo(serial) + ["pull", remoto, local])
    run_adb(env, alvo(serial) + ["shell", "rm", remoto])
    if rc != 0:
        erro("pull falhou: %s" % err.strip())
    print("screenshot: %s (%d bytes)" % (local, os.path.getsize(local)))
    log_ok(pasta, "foto de %s" % serial)
    return 0


def cmd_grava(env, serial, resto):
    serial = exige_device(env, serial)
    seg = int(resto[0]) if resto else 10
    if not 1 <= seg <= 180:
        erro("duracao fora do range 1..180 segundos.")
    pasta = pasta_saida()
    remoto = "/sdcard/adb-swiss-%d.mp4" % int(time.time())
    print("gravando %ds... (ctrl+c nao interrompe; aguarde)" % seg)
    rc, _, err = run_adb(env, alvo(serial) + ["shell", "screenrecord", "--time-limit", str(seg), remoto],
                         timeout=seg + 60)
    if rc != 0:
        erro("screenrecord falhou no device: %s" % err.strip())
    local = os.path.join(pasta, "screenrecord.mp4")
    rc, _, err = run_adb(env, alvo(serial) + ["pull", remoto, local], timeout=300)
    run_adb(env, alvo(serial) + ["shell", "rm", remoto])
    if rc != 0:
        erro("pull falhou: %s" % err.strip())
    print("gravacao: %s (%d bytes)" % (local, os.path.getsize(local)))
    log_ok(pasta, "screenrecord %ds de %s" % (seg, serial))
    return 0


def cmd_backup(env, serial, resto):
    serial = exige_device(env, serial)
    pasta = pasta_saida()
    if resto:
        pkg = resto[0]
        alvo_arq = os.path.join(pasta, "backup-%s.ab" % pkg.replace("/", "_"))
        args = ["backup", "-f", alvo_arq, "-noapk", "-noshared", pkg]
    else:
        alvo_arq = os.path.join(pasta, "backup-full.ab")
        args = ["backup", "-f", alvo_arq, "-all", "-apk", "-obb", "-shared"]
    print("aguardando confirmacao no aparelho (tela de backup do android)...")
    rc, _, err = run_adb(env, alvo(serial) + args, timeout=600)
    if rc != 0:
        erro("adb backup retornou rc=%d: %s" % (rc, err.strip()))
    if not os.path.isfile(alvo_arq) or os.path.getsize(alvo_arq) == 0:
        erro("backup vazio ou negado no aparelho (confirmacao recusada / nao suportado neste android).")
    print("backup: %s (%d bytes)" % (alvo_arq, os.path.getsize(alvo_arq)))
    log_ok(pasta, "backup de %s" % (resto[0] if resto else "tudo"))
    return 0


def cmd_puxa(env, serial, resto):
    serial = exige_device(env, serial)
    if not resto:
        erro("uso: puxa <pacote> [destino]  — ex: puxa com.whatsapp.w4b ./dados")
    pkg = resto[0]
    dest = resto[1] if len(resto) > 1 else os.path.join(pasta_saida(), pkg.replace("/", "_"))
    os.makedirs(dest, exist_ok=True)
    tentativas = [
        ("run-as (app debugavel)", ["shell", "run-as", pkg, "ls", "files"], "files"),
        ("/sdcard/Android/data (externo)", ["shell", "test", "-d", "/sdcard/Android/data/" + pkg], "/sdcard/Android/data/" + pkg),
        ("/data/data (exige root no device)", ["shell", "test", "-d", "/data/data/" + pkg], "/data/data/" + pkg),
    ]
    for nome, probe, caminho in tentativas:
        rc, _, _ = run_adb(env, alvo(serial) + probe)
        if rc != 0:
            print(".. %s: sem acesso" % nome)
            continue
        alvo_pull = caminho
        if caminho == "files":
            rc, out, _ = run_adb(env, alvo(serial) + ["shell", "run-as", pkg, "sh", "-c",
                                                      "cp -r files /sdcard/adb-swiss-pull 2>/dev/null; echo ok"])
            run_adb(env, alvo(serial) + ["shell", "run-as", pkg, "sh", "-c",
                                         "cat files/..* 2>/dev/null >/dev/null; true"])
            alvo_pull = "/sdcard/adb-swiss-pull"
        print(">> %s: acessivel. puxando..." % nome)
        rc, _, err = run_adb(env, alvo(serial) + ["pull", alvo_pull, dest], timeout=600)
        if caminho == "files":
            run_adb(env, alvo(serial) + ["shell", "run-as", pkg, "sh", "-c", "rm -rf /sdcard/adb-swiss-pull"])
            run_adb(env, alvo(serial) + ["shell", "rm", "-rf", "/sdcard/adb-swiss-pull"])
        if rc != 0:
            erro("pull falhou: %s" % err.strip())
        print("dados em: %s" % dest)
        log_ok(dest, "pull de %s via %s" % (pkg, nome))
        return 0
    erro("nenhum caminho acessivel para %s (app nao debugavel, sem root, sem dados externos)." % pkg)


def cmd_instala(env, serial, resto):
    serial = exige_device(env, serial)
    if not resto:
        erro("uso: instala <arquivo.apk> [--reinstala]")
    apk = resto[0]
    if not os.path.isfile(apk):
        erro("apk nao encontrado: %s" % apk)
    args = ["install"] + (["-r"] if "--reinstala" in resto[1:] else []) + [apk]
    rc, out, err = run_adb(env, alvo(serial) + args, timeout=600)
    saida = out + err
    falhas = {"INSTALL_FAILED_OLDER_SDK": "sdk do aparelho abaixo do minimo do apk",
              "INSTALL_FAILED_NEWER_SDK": "sdk do aparelho acima do suportado",
              "INSTALL_FAILED_NO_MATCHING_ABIS": "arquitetura incompativel (abi)",
              "INSTALL_PARSE_FAILED_NOT_APK": "arquivo nao e um apk valido",
              "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "assinatura divergente do app ja instalado",
              "INSTALL_FAILED_INSUFFICIENT_STORAGE": "espaco insuficiente no aparelho"}
    for codigo, msg in falhas.items():
        if codigo in saida:
            erro("%s: %s" % (codigo, msg))
    if rc != 0 or "Success" not in saida:
        erro("install falhou (rc=%d): %s" % (rc, saida.strip()[-300:]))
    print("instalado: %s" % apk)
    return 0


def cmd_desinstala(env, serial, resto):
    serial = exige_device(env, serial)
    if not resto:
        erro("uso: desinstala <pacote> [--mantem-dados]")
    pkg = resto[0]
    args = ["uninstall"] + (["-k"] if "--mantem-dados" in resto[1:] else []) + [pkg]
    rc, out, err = run_adb(env, alvo(serial) + args)
    if "Success" not in (out + err):
        erro("uninstall falhou: %s" % (out + err).strip()[-200:])
    print("desinstalado: %s" % pkg)
    return 0


def cmd_espelha(env, serial, _resto):
    serial = exige_device(env, serial)
    scr = shutil.which("scrcpy")
    if not scr:
        erro("scrcpy nao encontrado no PATH. instale: apt install scrcpy (ou brew install scrcpy).")
    print("espelhando %s (ctrl+c para encerrar)..." % serial)
    rc = subprocess.call([scr] + (["-s", serial] if serial else []))
    return rc


def cmd_ajuda(_env, _serial, _resto):
    print("""adb-swiss v%s — canivete suico do adb
uso: adb_swiss.py [ -s SERIAL ] [ --adbroot DIR ] <comando> [args]
     adb_swiss.py            -> menu interativo

comandos:
  dispositivos                  lista aparelhos visiveis
  info                          ficha tecnica do aparelho
  foto                          screenshot -> pasta de saida
  grava [1..180]                screenrecord (default 10s)
  backup [pacote]               backup full (-all -apk -obb -shared) ou de um pacote
  puxa <pacote> [destino]       dados de app: run-as -> /sdcard/Android/data -> /data/data
  instala <apk> [--reinstala]   instala, mapeando erros comuns
  desinstala <pkg> [--mantem-dados]
  espelha                       scrcpy se presente
  menu                          menu interativo
saida padrao: %s/<timestamp>/ com operacoes.log
""" % (VERSAO, OUT_RAIZ))
    return 0


ACOES = {"info": cmd_info, "foto": cmd_foto, "grava": cmd_grava, "backup": cmd_backup,
         "puxa": cmd_puxa, "instala": cmd_instala, "desinstala": cmd_desinstala,
         "espelha": cmd_espelha, "dispositivos": cmd_dispositivos, "ajuda": cmd_ajuda}


def menu(env, serial):
    while True:
        lista = dispositivos(env)
        estado = "conectado: %s" % lista[0][0] if lista else "nenhum dispositivo"
        print("""
== adb-swiss v%s | %s ==
 1) info             2) foto            3) grava
 4) backup           5) puxa dados      6) instala apk
 7) desinstala       8) espelha (scrcpy) 9) dispositivos
 0) sair
""" % (VERSAO, estado))
        try:
            op = input("escolha> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if op == "0":
            return 0
        escolha = {"1": "info", "2": "foto", "3": "grava", "4": "backup", "5": "puxa",
                   "6": "instala", "7": "desinstala", "8": "espelha", "9": "dispositivos"}.get(op)
        if not escolha:
            print("opcao invalida.")
            continue
        try:
            ACOES[escolha](env, serial, [])
        except SystemExit:
            pass


def main(argv):
    serial = os.environ.get("ANDROID_SERIAL") or None
    adbroot = os.environ.get("ADBROOT") or ("/tmp/adbroot" if os.path.isdir("/tmp/adbroot") else None)
    args = list(argv)
    if "-s" in args:
        i = args.index("-s")
        serial = args[i + 1]
        del args[i:i + 2]
    if "--adbroot" in args:
        i = args.index("--adbroot")
        adbroot = args[i + 1]
        del args[i:i + 2]
    env = monta_env(adbroot)
    if not achar_adb(env):
        print("ERRO: adb nao encontrado no PATH.")
        print(" instale android-tools (apt install adb) ou baixe platform-tools;")
        print(" ou aponte --adbroot DIR / ADBROOT=DIR para uma arvore extraida.")
        return 127
    if not args or args[0] == "menu":
        return menu(env, serial)
    comando = args[0]
    if comando not in ACOES:
        print("comando desconhecido: %s" % comando)
        cmd_ajuda(env, serial, [])
        return 2
    try:
        return ACOES[comando](env, serial, args[1:])
    except SystemExit as e:
        return e.code or 0
    except KeyboardInterrupt:
        print("\ninterrompido.")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
