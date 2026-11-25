# Upload HM-SEC to GitHub using SSH

The local project is in `/home/hamid/Documents/ChatGPT/HM_SEC`.
This guide can also be used for future uploads from the prepared local repository.
The commands below assume your GitHub username is **hamidelmarrouni** (from local Git configuration).
Replace it if your intended account is different.

## 1. Create an empty repository

Open https://github.com/new and create **HM-SEC**, with **Public** visibility.
Leave **Add a README**, **Add .gitignore**, and **Choose a license** unchecked:
those files are already in this project.
SSH pushes code to a repository; it does not create the repository on GitHub.

## 2. Verify your existing SSH access

You already have SSH public-key files on this machine. Start by testing your existing setup:

```sh
ssh -T git@github.com
```

A successful response says `Hi USERNAME! You've successfully authenticated...`.
GitHub intentionally returns exit code 1 for this successful test because it does not provide shell access.
Check that USERNAME is the account where you created HM-SEC.

For a first connection, verify the displayed host fingerprint against
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
before accepting it. Do not disable SSH host-key checking.

If authentication fails, add the matching **public** key to GitHub at
https://github.com/settings/keys. To display your default public key:

```sh
cat ~/.ssh/id_ed25519.pub
```

Only copy the `.pub` file. Never upload or share the private key.
If you use a different key/account, configure your SSH client for that identity first.
See https://docs.github.com/en/authentication/connecting-to-github-with-ssh/testing-your-ssh-connection.

## 3. Commit and upload the prepared files

```sh
cd /home/hamid/Documents/ChatGPT/HM_SEC
git add .
git diff --cached --stat
git commit -m "Package HM-SEC with portable Docker setup"
bash scripts/push-github.sh hamidelmarrouni
```

The helper requires a clean `main` branch, sets `origin` only if missing, and pushes without forcing.
It stops if an existing origin points somewhere else. It never stages new files automatically.

Equivalent direct commands (add origin only if it is not already configured):

```sh
cd /home/hamid/Documents/ChatGPT/HM_SEC
git status
git add .
git commit -m "Package HM-SEC with portable Docker setup"
git remote add origin git@github.com:hamidelmarrouni/HM-SEC.git
git push -u origin main
```

Run **either** the helper or the direct commands, not both. If `origin` already exists,
inspect it with `git remote -v`; do not blindly replace an unrelated remote.

## 4. Verify

Open https://github.com/hamidelmarrouni/HM-SEC and check the README and files.
The Validate workflow runs automatically. The Full Docker integration workflow can be started
manually from Actions; local verification results are in `docs/VALIDATION.md`.

For later changes, review `git status` and the diff, then stage only intended source files,
commit, and run `git push`. Runtime secrets, uploaded media, databases, cookies, and keys
are excluded by `.gitignore`.
