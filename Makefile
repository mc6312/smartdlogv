packer = 7z
pack = $(packer) a -mx=9
arcx = .7z
basename = smartdlogv
docs = COPYING README.md Changelog
srcs = $(basename).py $(basename)-mail.sh
arcname = $(basename)$(arcx)
backupdir = ~/shareddocs/pgm/python/
srcversion = smartdlogv
version = $(shell python3 -c 'from $(srcversion) import VERSION; print(VERSION)')
branch = $(shell git symbolic-ref --short HEAD)
srcarcname = $(basename)-$(branch)-src$(arcx)

archive:
	$(pack) $(srcarcname) *.py *.sh *. Makefile *.geany $(docs)
distrib:
	$(eval distname = $(basename)-$(version)$(arcx))
	$(pack) $(distname) $(srcs) $(docs)
backup:
	make archive
	mv $(srcarcname) $(backupdir)
update:
	$(packer) x -y $(backupdir)$(srcarcname)
commit:
	git commit -a -uno -m "$(version)"
