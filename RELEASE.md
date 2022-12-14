# How to create a new release for DCCUtils_server

We release DCCUtils_server versions through Github. Every time a new version is ready, we
follow this process:

1. Up the version number located the `dccutils_server/__version__` file.
2. Rebase on the main branch.
2. Push changes to `main` branch.
3. Build the package from the sources
4. Tag the commit and push the changes to Github
5. Publish the package on Pypi

You can run the following script to perform these commands at once:

```bash
release_number=0.1.0
git pull --rebase origin main
echo "__version__ = \"$release_number\"" > dccutils_server/__version__.py
git commit dccutils_server/__version__.py -m $release_number
git tag v$release_number
git push origin main --tag
python setup.py bdist_wheel --universal
twine upload dist/dccutils_server-$release_number-py2.py3-none-any.whl
```
