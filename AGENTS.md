# QNX Pi development

This project controls one headless QNX Pi through the local SSH alias `qnxpi`.

- Read `TARGET.md` before touching the QNX Pi.
- Connect with `ssh -o BatchMode=yes -o ConnectTimeout=20 qnxpi`.
- Use the globally installed official QNX skills, starting with `qnx-porting`,
  for QNX porting or package work.
- Do not change the Railway reverse tunnel or `/boot/onboot` unless the user
  explicitly asks for connectivity maintenance.
- Use direct SSH for short commands.
- Use the persistent runner for builds, tests, or other commands that should
  survive a dropped SSH session.
- Never place private keys, tokens, Wi-Fi credentials, or authentication state
  in this repository.
