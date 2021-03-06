#!/usr/bin/python

from __future__ import print_function

from optparse import OptionParser
import os
from subprocess import call, Popen, PIPE
import sys
import zipfile

# Due to "git archive" not supporting archiving of submodules in
# addition to the base tree, this requires additional support in order
# to create a complete and functional source archive.
#
# This script archives the base tree, and then uses "git submodule
# foreach" to archive each submodule separately, setting the correct
# path prefix for each archive, so that they may all be unpacked in
# the same root to result in a complete and functional source tree.
# It then repacks each of these zip files into a single zip which is
# the source release, taking care to preserve timestamps and exectute
# permissions, etc.  This is done via ZipInfo objects, and the
# repacking is done entirely in memory so that this should work on any
# platform irrespective of filesystem support for the archive
# attributes.  It excludes .gitignore files at this point to avoid
# polluting the release with version control files.


GITVERSION_XML = """<?xml version="1.0" encoding="utf-8"?>
<project name="gitversion" basedir=".">
    <property name="release.version" value="%s"/>
    <property name="release.shortversion" value="%s"/>
    <property name="vcs.shortrevision" value="%s"/>
    <property name="vcs.revision" value="%s"/>
    <property name="vcs.date" value="%s"/>
</project>
"""

GITVERSION_CMAKE = """set(OME_VERSION "%s")
set(OME_VERSION_SHORT "%s")
set(OME_VCS_SHORTREVISION "%s")
set(OME_VCS_REVISION "%s")
set(OME_VCS_DATE %s)
set(OME_VCS_DATE_S "%s")
"""

if __name__ == "__main__":

    parser = OptionParser()
    parser.add_option(
        "--release", action="store", type="string", dest="release")
    parser.add_option(
        "--bioformats-version", action="store", type="string",
        dest="bioformats_version")
    parser.add_option(
        "--bioformats-shortversion", action="store", type="string",
        dest="bioformats_shortversion")
    parser.add_option(
        "--bioformats-vcsshortrevision", action="store", type="string",
        dest="bioformats_vcsshortrevision")
    parser.add_option(
        "--bioformats-vcsrevision", action="store", type="string",
        dest="bioformats_vcsrevision")
    parser.add_option(
        "--bioformats-vcsdate", action="store", type="string",
        dest="bioformats_vcsdate")
    parser.add_option(
        "--bioformats-vcsdate-unix", action="store", type="string",
        dest="bioformats_vcsdate_unix")
    parser.add_option(
        "--target", action="store", type="string", dest="target")

    (options, args) = parser.parse_args(sys.argv)

    options.target = os.path.abspath(options.target)

    version = options.bioformats_version
    shortversion = options.bioformats_shortversion
    vcsdate = options.bioformats_vcsdate
    vcsshortrevision = options.bioformats_vcsshortrevision
    vcsrevision = options.bioformats_vcsrevision

    prefix = "%s-%s" % (options.release, version)

    if not os.path.exists('.git'):
        raise Exception('Releasing is only possible from a git repository')

    print("Releasing %s" % (prefix))
    sys.stdout.flush()

    # Create base archive
    base_archive_status = call([
        'git', 'archive', '--format', 'zip',
        '--prefix', "%s/" % (prefix),
        '--output', "%s/%s-base.zip" % (options.target, prefix),
        'HEAD'])
    if base_archive_status != 0:
        raise Exception('Failed to create git base archive')

    zips = list(["%s/%s-base.zip" % (options.target, prefix)])

    # Create submodule archives
    submodule_archive = Popen([
        'git', 'submodule', 'foreach', '--quiet', '--recursive',
        ("npath=\"$(echo \"$path\" | tr / _)\"; "
         "zip=\"%s/%s-submod-${npath}.zip\"; "
         "git archive --format zip --prefix \"%s/${path}/\""
         " --output \"${zip}\" HEAD || exit 1; "
         "echo \"${zip}\"") % (options.target, prefix, prefix)],
        stdout=PIPE)
    submodule_zips = submodule_archive.communicate()[0]
    if submodule_archive.returncode != 0:
        raise Exception('Failed to create git submodule archives')

    zips.extend(submodule_zips.splitlines())

    # Create destination zip file
    print("  - creating %s/%s.zip" % (options.target, prefix))
    sys.stdout.flush()
    basezip = zipfile.ZipFile("%s/%s.zip" % (options.target, prefix), 'w')

    # Repack each of the separate zips into the destination zip
    for name in zips:
        subzip = zipfile.ZipFile(name, 'r')
        print("  - repacking %s" % (name))
        sys.stdout.flush()
        # Iterate over the ZipInfo objects from the archive
        for info in subzip.infolist():
            # Skip unwanted git and travis files
            if (os.path.basename(info.filename) == '.gitignore' or
                    os.path.basename(info.filename) == '.gitmodule' or
                    os.path.basename(info.filename) == '.travis.yml'):
                continue
            # Skip files for which we don't have source in this repository, for GPL compliance
            if (options.release.endswith("-dfsg") and
                (os.path.splitext(info.filename)[1] == ".jar" or
                 os.path.splitext(info.filename)[1] == ".dll" or
                 os.path.splitext(info.filename)[1] == ".dylib" or
                 os.path.splitext(info.filename)[1] == ".so")):
                continue
            if (options.release.endswith("-dfsg") and
                info.filename.startswith("%s/components/xsd-fu/python/genshi" % (prefix))):
                continue
            print("File: %s" % (info.filename))
            # Repack a single zip object; preserve the metadata
            # directly via the ZipInfo object and rewrite the content
            # (which unfortunately requires decompression and
            # recompression rather than a direct copy)
            basezip.writestr(info, subzip.open(info.filename).read())

        # Close zip or else the remove will fail on Windows
        subzip.close()

        # Remove repacked zip
        os.remove(name)

    # Embed release number
    basezip.writestr(
        "%s/ant/gitversion.xml" % (prefix),
        GITVERSION_XML % (
            options.bioformats_version, options.bioformats_shortversion,
            options.bioformats_vcsshortrevision,
            options.bioformats_vcsrevision,
            options.bioformats_vcsdate))
    basezip.writestr(
        "%s/cpp/cmake/GitVersion.cmake" % (prefix),
        GITVERSION_CMAKE % (
            options.bioformats_version, options.bioformats_shortversion,
            options.bioformats_vcsshortrevision,
            options.bioformats_vcsrevision,
            options.bioformats_vcsdate_unix, options.bioformats_vcsdate))
