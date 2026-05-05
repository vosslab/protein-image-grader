set | grep -q '^BASH_VERSION=' || echo "use bash for your shell"
set | grep -q '^BASH_VERSION=' || exit 1

# Note: BASHRC unsets PYTHONPATH
source ~/.bashrc

# Set Python environment optimizations
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Make the repo root importable so `import protein_image_grader...` works
# from scripts in tools/ and from the repo root.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$REPO_ROOT" ]; then
	if [ -z "$PYTHONPATH" ]; then
		export PYTHONPATH="$REPO_ROOT"
	else
		export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"
	fi
fi
unset REPO_ROOT

