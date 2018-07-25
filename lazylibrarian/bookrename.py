#  This file is part of Lazylibrarian.
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.


import os

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.common import safe_move
from lazylibrarian.formatter import plural, is_valid_booktype, check_int, replace_all, getList, \
    makeUnicode, makeBytestr, multibook

try:
    from lib.tinytag import TinyTag
except ImportError:
    TinyTag = None


# Need to remove characters we don't want in the filename BEFORE adding to EBOOK_DIR
# as windows drive identifiers have colon, eg c:  but no colons allowed elsewhere?
__dic__ = {'<': '', '>': '', '...': '', ' & ': ' ', ' = ': ' ', '?': '', '$': 's',
           ' + ': ' ', '"': '', ',': '', '*': '', ':': '', ';': '', '\'': '', '//': '/', '\\\\': '\\'}


def audioRename(bookid):
    for item in ['$Part', '$Title']:
        if item not in lazylibrarian.CONFIG['AUDIOBOOK_DEST_FILE']:
            logger.error("Unable to audioRename, check AUDIOBOOK_DEST_FILE")
            return ''

    myDB = database.DBConnection()
    cmd = 'select AuthorName,BookName,AudioFile from books,authors where books.AuthorID = authors.AuthorID and bookid=?'
    exists = myDB.match(cmd, (bookid,))
    if exists:
        book_filename = exists['AudioFile']
        if book_filename:
            r = os.path.dirname(book_filename)
        else:
            logger.debug("No filename for %s in audioRename %s" % bookid)
            return ''
    else:
        logger.debug("Invalid bookid in audioRename %s" % bookid)
        return ''

    if not TinyTag:
        logger.warn("TinyTag library not available")
        return ''

    cnt = 0
    parts = []
    author = ''
    book = ''
    total = 0
    audio_file = ''
    abridged = ''
    for f in os.listdir(makeBytestr(r)):
        f = makeUnicode(f)
        if is_valid_booktype(f, booktype='audiobook'):
            cnt += 1
            audio_file = f
            try:
                id3r = TinyTag.get(os.path.join(r, f))
                performer = id3r.artist
                composer = id3r.composer
                albumartist = id3r.albumartist
                book = id3r.album
                title = id3r.title
                track = id3r.track
                total = id3r.track_total

                track = check_int(track, 0)
                total = check_int(total, 0)

                if performer:
                    performer = performer.strip()
                else:
                    performer = ''
                if composer:
                    composer = composer.strip()
                else:
                    composer = ''
                if book:
                    book = book.strip()
                else:
                    book = ''
                if albumartist:
                    albumartist = albumartist.strip()
                else:
                    albumartist = ''

                if composer:  # if present, should be author
                    author = composer
                elif performer:  # author, or narrator if composer == author
                    author = performer
                elif albumartist:
                    author = albumartist
                if author and book:
                    parts.append([track, book, author, f])
                if not abridged:
                    for tag in [book, title, albumartist, performer, composer]:
                        if 'unabridged' in tag.lower():
                            abridged = 'Unabridged'
                            break
                if not abridged:
                    for tag in [book, title, albumartist, performer, composer]:
                        if 'abridged' in tag.lower():
                            abridged = 'Abridged'
                            break

            except Exception as e:
                logger.error("tinytag %s %s" % (type(e).__name__, str(e)))
                pass
            finally:
                if not abridged:
                    if 'unabridged' in audio_file.lower():
                        abridged = 'Unabridged'
                        break
                if not abridged:
                    if 'abridged' in audio_file.lower():
                        abridged = 'Abridged'
                        break

    logger.debug("%s found %s audiofile%s" % (exists['BookName'], cnt, plural(cnt)))

    if cnt == 1 and not parts:  # single file audiobook
        parts = [1, exists['BookName'], exists['AuthorName'], audio_file]

    if cnt != len(parts):
        logger.warn("%s: Incorrect number of parts (found %i from %i)" % (exists['BookName'], len(parts), cnt))
        return book_filename

    if total and total != cnt:
        logger.warn("%s: Reported %i parts, got %i" % (exists['BookName'], total, cnt))
        return book_filename

    # check all parts have the same author and title
    if len(parts) > 1:
        for part in parts:
            if part[1] != book:
                logger.warn("%s: Inconsistent title: [%s][%s]" % (exists['BookName'], part[1], book))
                return book_filename
            if part[2] != author:
                logger.warn("%s: Inconsistent author: [%s][%s]" % (exists['BookName'], part[2], author))
                return book_filename

    # do we have any track info (value is 0 if not)
    if parts[0][0] == 0:
        tokmatch = ''
        # try to extract part information from filename. Search for token style of part 1 in this order...
        for token in [' 001.', ' 01.', ' 1.', ' 001 ', ' 01 ', ' 1 ', '01']:
            if tokmatch:
                break
            for part in parts:
                if token in part[3]:
                    tokmatch = token
                    break
        if tokmatch:  # we know the numbering style, get numbers for the other parts
            cnt = 0
            while cnt < len(parts):
                cnt += 1
                if tokmatch == ' 001.':
                    pattern = ' %s.' % str(cnt).zfill(3)
                elif tokmatch == ' 01.':
                    pattern = ' %s.' % str(cnt).zfill(2)
                elif tokmatch == ' 1.':
                    pattern = ' %s.' % str(cnt)
                elif tokmatch == ' 001 ':
                    pattern = ' %s ' % str(cnt).zfill(3)
                elif tokmatch == ' 01 ':
                    pattern = ' %s ' % str(cnt).zfill(2)
                elif tokmatch == ' 1 ':
                    pattern = ' %s ' % str(cnt)
                else:
                    pattern = '%s' % str(cnt).zfill(2)
                # standardise numbering of the parts
                for part in parts:
                    if pattern in part[3]:
                        part[0] = cnt
                        break

    parts.sort(key=lambda x: x[0])
    # check all parts are present
    cnt = 0
    while cnt < len(parts):
        if parts[cnt][0] != cnt + 1:
            logger.warn("%s: No part %i found" % (exists['BookName'], cnt + 1))
            return book_filename
        cnt += 1

    if abridged:
        abridged = ' (%s)' % abridged
    # if we get here, looks like we have all the parts needed to rename properly
    seriesinfo = nameVars(bookid, abridged)
    dest_path = seriesinfo['FolderName']
    dest_dir = lazylibrarian.DIRECTORY('Audio')
    dest_path = os.path.join(dest_dir, dest_path)
    if r != dest_path:
        try:
            dest_path = safe_move(r, dest_path)
            r = dest_path
        except Exception as why:
            if not os.path.isdir(dest_path):
                logger.error('Unable to create directory %s: %s' % (dest_path, why))

    with open(os.path.join(dest_path, 'playlist.ll'), 'w') as pl:
        for part in parts:
            pattern = seriesinfo['AudioFile']
            pattern = pattern.replace(
                '$Part', str(part[0]).zfill(len(str(len(parts))))).replace(
                '$Total', str(len(parts)))
            pattern = ' '.join(pattern.split()).strip()
            pattern = pattern + os.path.splitext(part[3])[1]
            pl.write(pattern + '\n')
            n = os.path.join(r, pattern)
            o = os.path.join(r, part[3])
            if o != n:
                try:
                    n = safe_move(o, n)
                    if part[0] == 1:
                        book_filename = n  # return part 1 of set
                    logger.debug('%s: audioRename [%s] to [%s]' % (exists['BookName'], o, n))

                except Exception as e:
                    logger.error('Unable to rename [%s] to [%s] %s %s' % (o, n, type(e).__name__, str(e)))
    return book_filename


def stripspaces(pathname):
    # windows doesn't allow directory names to end in a space or a period
    # but allows starting with a period (not sure about starting with a space but it looks messy anyway)
    parts = pathname.split(os.sep)
    new_parts = []
    for part in parts:
        while part and part[-1] in ' .':
            part = part[:-1]
        part = part.lstrip(' ')
        new_parts.append(part)
    pathname = os.sep.join(new_parts)
    return pathname


def bookRename(bookid):
    myDB = database.DBConnection()
    cmd = 'select AuthorName,BookName,BookFile from books,authors where books.AuthorID = authors.AuthorID and bookid=?'
    exists = myDB.match(cmd, (bookid,))
    if not exists:
        logger.debug("Invalid bookid in bookRename %s" % bookid)
        return ''

    f = exists['BookFile']
    if not f:
        logger.debug("No filename for %s in BookRename %s" % bookid)
        return ''

    r = os.path.dirname(f)
    if not lazylibrarian.CONFIG['CALIBRE_RENAME']:
        try:
            # noinspection PyTypeChecker
            calibreid = r.rsplit('(', 1)[1].split(')')[0]
            if not calibreid.isdigit():
                calibreid = ''
        except IndexError:
            calibreid = ''

        if calibreid:
            msg = '[%s] looks like a calibre directory: not renaming book' % os.path.basename(r)
            logger.debug(msg)
            return f

    reject = multibook(r)
    if reject:
        logger.debug("Not renaming %s, found multiple %s" % (f, reject))
        return f

    seriesinfo = nameVars(bookid)
    dest_path = seriesinfo['FolderName']
    dest_dir = lazylibrarian.DIRECTORY('eBook')
    dest_path = os.path.join(dest_dir, dest_path)
    dest_path = stripspaces(dest_path)
    oldpath = r

    if oldpath != dest_path:
        try:
            dest_path = safe_move(oldpath, dest_path)
        except Exception as why:
            if not os.path.isdir(dest_path):
                logger.error('Unable to create directory %s: %s' % (dest_path, why))

    book_basename, prefextn = os.path.splitext(os.path.basename(f))
    new_basename = seriesinfo['BookFile']

    if ' / ' in new_basename:  # used as a separator in goodreads omnibus
        logger.warn("bookRename [%s] looks like an omnibus? Not renaming %s" % (new_basename, book_basename))
        new_basename = book_basename

    if book_basename != new_basename:
        # only rename bookname.type, bookname.jpg, bookname.opf, not cover.jpg or metadata.opf
        for fname in os.listdir(makeBytestr(dest_path)):
            fname = makeUnicode(fname)
            extn = ''
            if is_valid_booktype(fname, booktype='ebook'):
                extn = os.path.splitext(fname)[1]
            elif fname.endswith('.opf') and not fname == 'metadata.opf':
                extn = '.opf'
            elif fname.endswith('.jpg') and not fname == 'cover.jpg':
                extn = '.jpg'
            if extn:
                ofname = os.path.join(dest_path, fname)
                nfname = os.path.join(dest_path, new_basename + extn)
                if ofname != nfname:
                    try:
                        nfname = safe_move(ofname, nfname)
                        logger.debug("bookRename %s to %s" % (ofname, nfname))
                        oldname = os.path.join(oldpath, fname)
                        if oldname == exists['BookFile']:  # if we renamed/moved the preferred file, return new name
                            f = nfname
                    except Exception as e:
                        logger.error('Unable to rename [%s] to [%s] %s %s' %
                                     (ofname, nfname, type(e).__name__, str(e)))
    return f


def nameVars(bookid, abridged=''):
    """ Return name variables for a bookid as a dict of formatted strings
        The strings are configurable, but by default...
        Series returns ( Lord of the Rings 2 )
        FmtName returns Lord of the Rings (with added Num part if that's not numeric, eg Lord of the Rings Book One)
        FmtNum  returns Book #1 -    (or empty string if no numeric part)
        so you can combine to make Book #1 - Lord of the Rings
        PadNum is zero padded numeric part or empty string
        SerName and SerNum are the unformatted base strings
        PubYear is the publication year of the book or empty string
        SerYear is the publication year of the first book in the series or empty string
        """
    mydict = {}
    seriesnum = ''
    seriesname = ''
    myDB = database.DBConnection()
    cmd = 'SELECT SeriesID,SeriesNum,BookDate from member,books WHERE books.bookid = member.bookid and books.bookid=?'
    res = myDB.match(cmd, (bookid,))
    if res:
        seriesid = res['SeriesID']
        serieslist = getList(res['SeriesNum'])
        pubyear = res['BookDate']
        cmd = 'SELECT BookDate from member,books WHERE books.bookid = member.bookid and SeriesNum=1 and SeriesID=?'
        resDate = myDB.match(cmd, (seriesid,))
        if res:
            seryear = resDate['BookDate']
        else:
            seryear = ''
    elif bookid == 'test':
        seriesid = '66175'
        serieslist = ['3']
        pubyear = '1955'
        seryear = '1954'
        seriesname = 'The Lord of the Rings'
        mydict['Author'] = 'J.R.R. Tolkien'
        mydict['Title'] = 'The Fellowship of the Ring'
    else:
        seriesid = ''
        serieslist = []
        pubyear = ''
        seryear = ''

    if not pubyear or pubyear == '0000':
        pubyear = ''
    pubyear = pubyear[:4]  # googlebooks sometimes has month or full date

    if not seryear or seryear == '0000':
        seryear = ''
    seryear = seryear[:4]

    # might be "Book 3.5" or similar, just get the numeric part
    while serieslist:
        seriesnum = serieslist.pop()
        seriesnum = seriesnum.lstrip('#')
        try:
            _ = float(seriesnum)
            break
        except ValueError:
            seriesnum = ''
            pass

    padnum = ''
    if res and seriesnum == '':  # allow zero as valid seriesnum
        # couldn't figure out number, keep everything we got, could be something like "Book Two"
        serieslist = res['SeriesNum']
    elif seriesnum.isdigit():
        padnum = str(int(seriesnum)).zfill(2)
    else:
        try:
            padnum = str(float(seriesnum))
            if padnum[1] == '.':
                padnum = '0' + padnum
        except (ValueError, IndexError):
            padnum = ''

    if seriesid and bookid != 'test':
        cmd = 'SELECT SeriesName from series WHERE seriesid=?'
        res = myDB.match(cmd, (seriesid,))
        if res:
            seriesname = res['SeriesName']
            if seriesnum == '':  # allow zero as a seriesnum
                # add what we got back to end of series name
                if seriesname and serieslist:
                    seriesname = "%s %s" % (seriesname, serieslist)

    seriesname = ' '.join(seriesname.split())  # strip extra spaces
    if seriesname.isspace():  # but don't return just whitespace
        seriesname = ''

    if seriesname:
        fmtname = lazylibrarian.CONFIG['FMT_SERNAME'].replace('$SerName', seriesname).replace(
                                                              '$PubYear', pubyear).replace(
                                                              '$SerYear', seryear).replace(
                                                              '$$', ' ')
    else:
        fmtname = ''

    fmtname = ' '.join(fmtname.split())
    if fmtname.isspace():
        fmtname = ''

    if seriesnum != '':  # allow 0
        fmtnum = lazylibrarian.CONFIG['FMT_SERNUM'].replace('$SerNum', seriesnum).replace(
                                                            '$PubYear', pubyear).replace(
                                                            '$SerYear', seryear).replace(
                                                            '$PadNum', padnum).replace('$$', ' ')
    else:
        fmtnum = ''

    fmtnum = ' '.join(fmtnum.split())
    if fmtnum.isspace():
        fmtnum = ''

    if fmtnum != '' or fmtname:
        fmtseries = lazylibrarian.CONFIG['FMT_SERIES'].replace('$SerNum', seriesnum).replace(
                                                             '$SerName', seriesname).replace(
                                                             '$PadNum', padnum).replace(
                                                             '$PubYear', pubyear).replace(
                                                             '$SerYear', seryear).replace(
                                                             '$FmtName', fmtname).replace(
                                                             '$FmtNum', fmtnum).replace('$$', ' ')
        fmtseries = ' '.join(fmtseries.split())
    else:
        fmtseries = ''

    mydict['FmtName'] = fmtname
    mydict['FmtNum'] = fmtnum
    mydict['Series'] = fmtseries
    mydict['PadNum'] = padnum
    mydict['SerName'] = seriesname
    mydict['SerNum'] = seriesnum
    mydict['PubYear'] = pubyear
    mydict['SerYear'] = seryear
    mydict['Abridged'] = abridged

    if bookid != 'test':
        cmd = 'select AuthorName,BookName from books,authors where books.AuthorID = authors.AuthorID and bookid=?'
        exists = myDB.match(cmd, (bookid,))
        if exists:
            mydict['Author'] = exists['AuthorName']
            mydict['Title'] = exists['BookName']
        else:
            mydict['Author'] = ''
            mydict['Title'] = ''

    dest_path = replacevars(lazylibrarian.CONFIG['EBOOK_DEST_FOLDER'], mydict)
    dest_path = replace_all(dest_path, __dic__)
    mydict['FolderName'] = stripspaces(dest_path)

    bookfile = replacevars(lazylibrarian.CONFIG['EBOOK_DEST_FILE'], mydict)
    # replace all '/' not surrounded by whitespace with '_' as '/' is a directory separator
    # but also used in some multi-book titles
    slash = bookfile.find('/')
    while slash > 0:
        if bookfile[slash - 1] != ' ':
            if bookfile[slash + 1] != ' ':
                bookfile = bookfile[:slash] + '_' + bookfile[slash + 1:]
        slash = bookfile.find('/', slash + 1)
    mydict['BookFile'] = bookfile

    audiofile = replacevars(lazylibrarian.CONFIG['AUDIOBOOK_DEST_FILE'], mydict)
    slash = audiofile.find('/')
    while slash > 0:
        if audiofile[slash - 1] != ' ':
            if audiofile[slash + 1] != ' ':
                audiofile = audiofile[:slash] + '_' + audiofile[slash + 1:]
        slash = audiofile.find('/', slash + 1)
    if bookid == 'test':
        audiofile = audiofile.replace('$Part', '03').replace('$Total', '12')
    mydict['AudioFile'] = audiofile

    return mydict


def replacevars(base, mydict):
    res = base.replace(
        '$Author', mydict['Author']).replace(
        '$Title', mydict['Title']).replace(
        '$Series', mydict['Series']).replace(
        '$FmtName', mydict['FmtName']).replace(
        '$FmtNum', mydict['FmtNum']).replace(
        '$SerName', mydict['SerName']).replace(
        '$SerNum', mydict['SerNum']).replace(
        '$PadNum', mydict['PadNum']).replace(
        '$PubYear', mydict['PubYear']).replace(
        '$SerYear', mydict['SerYear']).replace(
        '$Abridged', mydict['Abridged']).replace(
        '$$', ' ')
    return ' '.join(res.split()).strip()
