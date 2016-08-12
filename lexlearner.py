#! /usr/bin/python3

import os, sys, re, pipes
from subprocess import call
from time import clock
from llconfig import *
sys.path.insert(0, os.path.join(lextools, 'scripts'))
import common

after_end_re = re.compile(r'\$.*?\^')
punct_tag_re = re.compile('<(guio|sent|cm)>')
open_cats_re = re.compile('<{}>'.format('>|<'.join(opencats)))

lm_fname = "/tmp/test.lm"

def tag_corpus(pair_data, source, target,
               pair_name, corpus_folder,
               corpus_name, data_folder):
    """
    Translate corpus up until pretransfer stage
    """
    # create partial translation pipeline
    pipe = pipes.Template()
    pipe.append('apertium -d "{}" {}-{}-tagger'.format(pair_data, source, target), '--')
    pipe.append('apertium-pretransfer', '--')

    # file names
    corpus_prefix = os.path.join(corpus_folder, corpus_name)
    ifname = os.path.join(corpus_folder,
                          '{}.{}.{}'.format(corpus_prefix, pair_name, source))
    ofname = os.path.join(data_folder, 
                          '{}.{}.tagged.{}'.format(corpus_name, pair_name, source))
    
    # translation
    linecount = 0
    with open(ifname, 'r', encoding='utf-8') as ifile,\
         pipe.open(ofname, 'w') as pipefile:
        for line in ifile:
            pipefile.write(line)
            linecount += 1
            if linecount == maxlines:
                break
    return linecount, ofname

def clean_tags(pair_name, sfname, tfname, source, target, corpus_name, data_folder):
    """
    Clean up and convert tags simultaneously in both corpora to be used in MGIZA
    """
    with open(sfname, 'r', encoding='utf-8') as sfile, \
         open(tfname, 'r', encoding='utf-8') as tfile, \
         open(sfname.replace('tagged', 'retagged'), 'w', encoding='utf-8') as sfile_re,\
         open(tfname.replace('tagged', 'retagged'), 'w', encoding='utf-8') as tfile_re:
        for sline, tline in zip(sfile, tfile):
            if '<' in sline + tline:
                sfile_re.write(after_end_re.sub('$ ^', sline.replace(' ', '~')))
                tfile_re.write(after_end_re.sub('$ ^', tline.replace(' ', '~')))

    ifname_prefix = os.path.join(data_folder, '{}.{}.retagged'.format(corpus_name, pair_name))
    ofname_prefix = os.path.join(data_folder, '{}.{}.tagged-clean'.format(corpus_name, pair_name))

    call(['perl', os.path.join(moses, 'clean-corpus-n.perl'), ifname_prefix,
          source, target, ofname_prefix, '1', '40'])

    return '{}.{}'.format(ofname_prefix, source), '{}.{}'.format(ofname_prefix, target)

def trim_tags(pair_data, source, target, lextools, ifname):
    """
    Trim individual tag sets to fit into some coarse-grained classes.
    """
    pipe = pipes.Template()
    pipe.append('{} {}.autobil.bin -p -t'.format(os.path.join(lextools, 'multitrans'),
                                                 os.path.join(pair_data, '{}-{}'.format(source, target))), '--')
    ofname = ifname.replace('tagged-clean', 'trimmed')

    pipe.copy(ifname, ofname)

    #with open(ifname, 'r', encoding='utf-8') as ifile,\
    #     pipe.open(ofname, 'w') as pipefile:
    #    for line in ifile:
    #        pipefile.write(line)
    return ofname

def get_default(line):
    lemma_tl = '';
    tags_tl = '';
    lemma_sl = '';
    tags_sl = '';
    state = 0;
    escaped = False;
    for c in line: #{
        if c == '^': #{
            state = 1; 
            continue;
        #}
        if c == '\\': #{
            escaped = True;
            continue;
        #}
        if c == '<': #{
            if state == 1: #{
                state = 2; 
            #}
            if state == 3: #{
                state = 4;
            #}
            continue;
        #}
        if c == '/' and state == 2 and not escaped: #{
            state = 3    
            continue;
        #}
        if c == '$' or (c == '/' and state > 2) and not escaped: #{
            break;
        #}

        if state == 1: #{
            lemma_sl = lemma_sl + c;
        elif state == 2: #{    
            if c == '>': #{
                tags_sl = tags_sl + '.'    
            elif c != '<': #{
                tags_sl = tags_sl + c;
            #}
                
        elif state == 3: #{
            lemma_tl = lemma_tl + c;    
        elif state == 4: #{
            if c == '>': #{
                tags_tl = tags_tl + '.'    
            elif c != '<': #{
                tags_tl = tags_tl + c;
            #}
        #}
    #}    
    tags_sl = tags_sl.strip('.');
    tags_tl = tags_tl.strip('.');

    return (lemma_sl, tags_sl, lemma_tl, tags_tl)

def prepare_data(pair_data, source, target, pair_name, data_folder):
    """
    Make rules for the words that must be translated unambiguously
    (i.e. that are not in open classes).
    """
    autobil_ambig = os.path.join(pair_data, '{}-{}.autobil.ambig.bin'.format(source, target))
    autobil_unambig = os.path.join(pair_data, '{}-{}.autobil.bin'.format(source, target))

    call(['lt-comp', 'lr', os.path.join(pair_data, 'apertium-{}.{}.dix'.format(pair_name, pair_name)), autobil_ambig])

    cwdir = os.getcwd()
    os.chdir(pair_data)
    call(['make', '{}-{}.autobil.bin'.format(source, target)])
    os.chdir(cwdir)

    if os.path.exists(os.path.join(pair_data, '.deps', 'en.dix')):
        dict_name = os.path.join(pair_data, '.deps', 'en.dix')
    else:
        dict_name = os.path.join(pair_data, 'apertium-{}.{}.dix'.format(pair_name, source))

    ambig_pipe = pipes.Template()
    ambig_pipe.append('{} {} -b -t'.format(os.path.join(lextools, 'multitrans'), autobil_ambig), '--')
    ambig_pipefname = os.path.join(data_folder, 'ambig')

    unambig_pipe = pipes.Template()
    unambig_pipe.append('{} {} -b -t'.format(os.path.join(lextools, 'multitrans'), autobil_unambig), '--')
    unambig_pipefname = os.path.join(data_folder, 'unambig')

    exp_dict_fname = os.path.join(data_folder, 'expanded')
    call(['lt-expand', dict_name, exp_dict_fname])
    with open(exp_dict_fname, 'r', encoding='utf-8') as exp_dict_file, \
         ambig_pipe.open(ambig_pipefname, 'w') as ambig_pipefile, \
         unambig_pipe.open(unambig_pipefname, 'w') as unambig_pipefile:
        for line in exp_dict_file:
            if 'REGEXP' not in line:
                line = line.strip().replace(':>:', ':').replace(':<:', ':')
                line = '^{}$\n'.format(line.split(':')[1])
                ambig_pipefile.write(line)
                unambig_pipefile.write(line)

    rules = set()
    with open(ambig_pipefname, 'r', encoding='utf-8') as ambig_pipefile, \
         open(unambig_pipefname, 'r', encoding='utf-8') as unambig_pipefile:
        for ambig_line, unambig_line in zip(ambig_pipefile, unambig_pipefile):
            combined_line = '{}\t{}'.format(ambig_line.strip(), unambig_line.strip())
            if combined_line.count('/') >= 3 and open_cats_re.search(combined_line) is None:
                rules.add(get_default(combined_line))

    rules = list(rules)
    rules.sort(key=lambda x: x[0].lower())   
    gdeffname = os.path.join(data_folder, 'global-defaults.{}-{}.lrx'.format(source, target))
    with open(gdeffname, 'w', encoding='utf-8') as gdeffile:
        gdeffile.write('<rules>\n')
        for rule in rules:
            gdeffile.write('  <rule><match lemma="{}" tags="{}"><select lemma="{}" tags="{}"/></match></rule>\n'.format(*rule))
        gdeffile.write('</rules>')

    call(['lrx-comp', gdeffname, os.path.join(data_folder, 'global-defaults.{}-{}.bin'.format(source, target))])

def is_ambiguous(bt):
    return any(len(token['tls']) > 1 for token in bt)

def align_corpus(pair_data, source, target, pair_name, corpus_name, data_folder):
    """
    Exactly what it says on the tin.
    """
    # fake language model
    open(lm_fname, 'w', encoding='utf-8').write('1\n2\n3')

    # align corpus
    ifname_prefix = os.path.join(data_folder, '{}.{}.trimmed'.format(corpus_name, pair_name))
    call(['perl', os.path.join(moses, 'train-model.perl'),
          '-mgiza', '-external-bin-dir', giza, 
          '-corpus', ifname_prefix, '-f', target, '-e', source,
          '-alignment', 'grow-diag-final-and', '-reordering', 'msd-bidirectional-fe', 
          '-lm', '0:5:{}:0'.format(lm_fname)])

    # extract phrase alignments
    pair = '{}-{}'.format(source, target)
    extract_pipe = pipes.Template()
    extract_pipe.append('zcat $IN', 'f-')
    extract_pipe.append(os.path.join(lextools, 'scripts', 'giza-to-moses.awk'), '--')

    giza_final = 'giza.{}.A3.final.gz'.format(os.path.join(pair, pair))
    phrases_fname = os.path.join(data_folder, 
                                 '{}.phrases.{}'.format(corpus_name, pair))
    phrasetable_fname = os.path.join(data_folder, 
                                     '{}.phrasetable.{}'.format(corpus_name, pair))
    
    extract_pipe.copy(giza_final, phrases_fname)

    cb_pipe = pipes.Template()
    cb_pipe.append('{} {}.autobil.bin -b'.format(os.path.join(lextools, 'multitrans'),
                                                 os.path.join(pair_data, pair)), '--')
    cb_pipe.append('lrx-proc -m ' + os.path.join(data_folder, 'global-defaults.{}.bin'.format(pair)), '--')
    clean_biltrans_fname = os.path.join(data_folder, '{}.clean-biltrans.{}'.format(corpus_name,  pair))

    with open(phrases_fname, 'r', encoding='utf-8') as pfile,\
         open(os.path.join('model', 'aligned.grow-diag-final-and'), 'r', encoding='utf-8') as agdfinal,\
         open(phrasetable_fname, 'w', encoding='utf-8') as ptfile,\
         cb_pipe.open(clean_biltrans_fname, 'w') as cb_pipefile:
        for phrase_info, alignment in zip(pfile, agdfinal):
            phrases = phrase_info.split('|||')
            ptfile.write('|||'.join(phrases[0:2] + [alignment]))
            cb_pipefile.write(phrases[1].replace('~', ' ') + '\n')

    # extract candidate sentences
    cand_fname = os.path.join(data_folder, '{}.candidates.{}'.format(corpus_name, pair))
    not_ambiguous = []
    lineno, total_valid, total_errors = 0, 0, 0
    with open(phrasetable_fname, 'r', encoding='utf-8') as ptfile,\
         open(clean_biltrans_fname, 'r', encoding='utf-8') as btfile,\
         open(cand_fname, 'w', encoding='utf-8') as candfile:
        for pt_line, bt_line in zip(ptfile, btfile):
            lineno += 1
            try:
                pt_line, bt_line = pt_line.strip(), bt_line.strip()

                if pt_line == '' or bt_line == '':
                    continue 

                row = pt_line.split('|||')
                bt = common.tokenise_biltrans_line(bt_line.strip())
                sl = common.tokenise_tagger_line(row[1].strip())
                tl = common.tokenise_tagger_line(row[0].strip())

                if not is_ambiguous(bt):
                    not_ambiguous.append(str(lineno))
                    if len(not_ambiguous) >= 10:
                        print("Not ambiguous: {}".format(' '.join(not_ambiguous)), file=sys.stderr)
                        not_ambiguous = []
                    continue

                if len(sl) < 2 and len(tl) < 2:
                    continue

                if len(sl) != len(bt):
                    print("len(sl) != len(bt)", file=sys.stderr)

                candfile.write('{}\t{}\n'.format(lineno, row[1].strip()))
                candfile.write('{}\t{}\n'.format(lineno, bt_line))
                candfile.write('{}\t{}\n'.format(lineno, row[0].strip()))
                candfile.write('{}\t{}\n'.format(lineno, row[2].strip()))
                candfile.write('-' * 80 + '\n')
                total_valid += 1
            except:
                print("error in line", lineno, file=sys.stderr)
                total_errors += 1
    print('total:', lineno, file=sys.stderr)
    print('valid: {} ({:.1%})'.format(total_valid, total_valid/lineno), file=sys.stderr)
    print('errors: {} ({:.1%})'.format(total_errors, total_errors/lineno), file=sys.stderr)

    # extract frequency lexicon
    sl_tl, ngrams = {}, {}
    with open(cand_fname, 'r', encoding='utf-8') as candfile:
        while True:
            try:
                cur_sl_row = common.tokenise_tagger_line(candfile.readline().strip().split('\t')[1])
                cur_bt_row = common.tokenise_biltrans_line(candfile.readline().strip().split('\t')[1])
                cur_tl_row = common.tokenise_tagger_line(candfile.readline().strip().split('\t')[1])
                cur_al_row = candfile.readline().strip().split('\t')[1].split(' ')
                candfile.readline()
            except IndexError:
                print("Something's wrong with {} ".format(candfile))
                break
            except EOFError:
                break

            for i, (slword, btword) in enumerate(zip(cur_sl_row, cur_bt_row)):
                if len(btword['tls']) > 1:
                    for al in cur_al_row:
                        al_sl = int(al.split('-')[1])
                        al_tl = int(al.split('-')[0])
                        if al_sl == i:
                            tlword = cur_tl_row[al_tl]
                            sl_tl.setdefault(slword, {})
                            sl_tl[slword].setdefault(tlword, 0)
                            sl_tl[slword][tlword] += 1

    freq_lex_fname = os.path.join(data_folder, '{}.lex.{}'.format(corpus_name, pair))
    with open(freq_lex_fname, 'w', encoding='utf-8') as freq_lex_file:
        for sl, tl_freq_dict in sl_tl.items():
            first_tag_sl = sl.split('<')[1].split('>')[0].strip()
            tl_sorted = sorted(tl_freq_dict, key=tl_freq_dict.get, reverse=True)
            first = True
            for tl in tl_sorted:
                if tl.startswith('*'):
                    print('tl word "{}" is unknown'.format(tl),  file=sys.stderr)
                    continue
                first_tag_tl = tl.split('<')[1].split('>')[0].strip()
                if first_tag_sl != first_tag_tl:
                    print('{} != {}'.format(first_tag_sl, first_tag_tl), file=sys.stderr)
                    continue
                if first:
                    freq_lex_file.write('{} ^{}$ ^{}$ @\n'.format(sl_tl[sl][tl], sl, tl))
                    first = False
                else:
                    freq_lex_file.write('{} ^{}$ ^{}$\n'.format(sl_tl[sl][tl], sl, tl))

    return cand_fname, freq_lex_fname

def read_freq_lex_file(freq_lex_fname):
    """
    Read and parse frequency lexicon.
    """
    sl_tl, sl_tl_defaults = {}, {}
    index, rindex = {}, {}
    trad_counter = {}
    with open(freq_lex_fname, 'r', encoding='utf-8') as freq_lex_file:
        for line in freq_lex_file:
            line = line.strip()
            if line != '':
                row = common.tokenise_tagger_line(line)
                sl = '^{}$'.format(row[0].lower())
                tl = '^{}$'.format(row[1].strip().lower())
                if tl.startswith('^*'):
                    tl = tl[:-3] + '$'
            
                sl_tl.setdefault(sl, [])
                trad_counter.setdefault(sl, 0)
                if '@' in line:
                    sl_tl_defaults[sl] = tl

                sl_tl[sl].append(tl)
                index[(sl, tl)] = trad_counter[sl]
                rindex[(sl, trad_counter[sl])] = tl
                trad_counter[sl] += 1

    return sl_tl, sl_tl_defaults, index, rindex

def ngram_count_patterns_maxent(cand_fname, freq_lex_fname, yasmet_data):
    event_fname = os.path.join(yasmet_data, 'events')
    ngram_fname = os.path.join(yasmet_data, 'ngrams')

    sl_tl, sl_tl_defaults, index, rindex = read_freq_lex_file(freq_lex_fname)

    ngrams = {}
    event_counter = 0
    features = {} # features[(slword, ['a', 'list'], tlword)] = 3
    feature_counter = 0

    with open(cand_fname, 'r', encoding='utf-8') as candfile,\
         open(event_fname, 'w', encoding='utf-8') as eventfile:
        while True:
            try:
                cur_sl_row = common.tokenise_tagger_line(candfile.readline().strip().split('\t')[1])
                cur_bt_row = common.tokenise_biltrans_line(candfile.readline().strip().split('\t')[1])
                cur_tl_row = common.tokenise_tagger_line(candfile.readline().strip().split('\t')[1])
                cur_al_row = candfile.readline().strip().split('\t')[1].split(' ')
                candfile.readline()
            except IndexError:
                break
            except EOFError:
                break

            for i, (slword, btword) in enumerate(zip(cur_sl_row, cur_bt_row)):
                slword = '^{}$'.format(slword.lower())
                if len(btword['tls']) > 1:
                    for al in cur_al_row:
                        al_sl = int(al.split('-')[1])
                        al_tl = int(al.split('-')[0])
                        if al_sl == i:

                            tlword = '^{}$'.format(cur_tl_row[al_tl].lower())

                            if tlword.startswith('^*') or slword.startswith('^*'):
                                # unknown word
                                continue

                            if slword not in sl_tl_defaults:
                                print('"{}" not in sl_tl_defaults, skipping'.format(slword), file=sys.stderr)
                                continue

                            if (slword, tlword) not in index:
                                print('Pair ({}, {}) not in index'.format(slword, tlword), file=sys.stderr)
                                continue

                            ngrams = {}
                            meevents = {} # events[slword][counter] = [feat, feat, feat];
                            meoutcomes = {} # meoutcomes[slword][counter] = tlword;

                            for j in range(1, max_ngrams):
                                pregram = ' '.join(('^{}$'.format(gram) for gram in cur_sl_row[i-j:i+1]))
                                postgram = ' '.join(('^{}$'.format(gram) for gram in cur_sl_row[i:i+j+1]))
                                roundgram = ' '.join(('^{}$'.format(gram) for gram in cur_sl_row[i-j:i+j+1]))

                                ngrams.setdefault(slword, {})
                                ngrams[slword].setdefault(pregram, {})
                                ngrams[slword].setdefault(postgram, {})
                                ngrams[slword].setdefault(roundgram, {})
                                ngrams[slword][pregram].setdefault(tlword, 0)
                                ngrams[slword][pregram][tlword] += 1
                                ngrams[slword][postgram].setdefault(tlword, 0)
                                ngrams[slword][postgram][tlword] += 1
                                ngrams[slword][roundgram].setdefault(tlword, 0)
                                ngrams[slword][roundgram][tlword] += 1

                            meevents.setdefault(slword, {})
                            meoutcomes.setdefault(slword, {})
                            meevents[slword].setdefault(event_counter, [])
                            meoutcomes[slword].setdefault(event_counter, '')

                            for ni in ngrams[slword]:
                                if ni not in features:
                                    feature_counter += 1
                                    features[ni] = feature_counter
                                meevents[slword][event_counter].append(features[ni])
                                #meevents[slword][event_counter].append(feat)
                                meoutcomes[slword][event_counter] = tlword
                    
                            if len(sl_tl[slword]) < 2:
                                continue

                            for event in meevents[slword]:
                                outline = str(index[(slword, meoutcomes[slword][event])]) + ' # '
                                for j in range(0,  len(sl_tl[slword])):
                                    for feature in meevents[slword][event]:
                                        outline = outline + str(feature) + ':' + str(j) + ' '
                                    outline = outline + ' # '
                                eventfile.write('{}\t{}\t{}\n'.format(slword, len(sl_tl[slword]), outline))
            event_counter += 1

    with open(ngram_fname, 'w', encoding='utf-8') as ngramfile:
        for feature, number in sorted(features.items(), key=lambda x: x[0]):
            ngramfile.write('{}\t{}\n'.format(number, feature))

    return event_fname, ngram_fname

def get_lambdas(yasmet_data, event_fname):
    """
    Learn weights with yasmet.
    """
    event_dict = {}
    min_ngrams = max_ngrams * 2 - 1
    with open(event_fname, 'r', encoding='utf-8') as eventfile:
        for line in eventfile:
            parts = line.strip().split('\t')
            if len(parts) == 3:
                word, count, event = parts
                event_dict.setdefault(word, (count, []))
                event_dict[word][1].append(event)

    print(sorted(event_dict.keys()))

    yasmet = os.path.join(lextools, 'yasmet')
    yasmet_pipe = pipes.Template()
    yasmet_pipe.append('{} -red {}'.format(yasmet, min_ngrams), '--')
    yasmet_pipe.append(yasmet, '--')
    all_lambdas_fname = os.path.join(yasmet_data, 'all-lambdas')
    tmp_flist = []

    with open(all_lambdas_fname, 'w', encoding='utf-8') as all_lambdas_file:
        for word, (count, events) in sorted(event_dict.items(), key=lambda x: x[0]):
            word_safe = word.replace('^', '').replace('$', '').replace('*', '.').replace('#~', '_')
            yasmet_tmp_fname = os.path.join(yasmet_data, 'tmp.yasmet.' + word_safe)
            lambdas_tmp_fname = os.path.join(yasmet_data, 'tmp.lambdas.' + word_safe)
            tmp_flist.extend([yasmet_tmp_fname, lambdas_tmp_fname])
            with open(yasmet_tmp_fname, 'w', encoding='utf-8') as tmp:
                tmp.write('{}\n'.format(count))
                for event in events:
                    tmp.write('{}\n'.format(event))
            yasmet_pipe.copy(yasmet_tmp_fname, lambdas_tmp_fname)
            with open(lambdas_tmp_fname, 'r', encoding='utf-8') as ltmp:
                for line in ltmp:
                    all_lambdas_file.write(word + ' ' + line)
    for fname in tmp_flist:
        os.remove(fname)
    return all_lambdas_fname, min_ngrams

def get_lemma_and_tags(word):
    """
    Parse a ^some#~word<n><sg><*>$ into ('some# word', 'n.sg.*')
    """
    parts = word.strip('^>$').replace('><', '.').split('<')
    return parts[0].replace('~', ' '), parts[1]

def make_xml_rule(weight, slword, ngram, tlword, lineno, ruleno):
    """
    Make a rule in xml format to output to final rule file.
    """
    if punct_tag_re.search(ngram):
        print('Punctuation in pattern "{}"'.format(ngram), file=sys.stderr)
        return None, lineno + 1, ruleno

    slword, tlword, ngram = slword.lower(), tlword.lower(), ngram.lower()
    pattern = ngram.split(' ')

    if ngram != '':
        if len(pattern) < 2:
            print('Pattern "{}" below minmatch'.format(ngram), file=sys.stderr)
            return None, lineno + 1, ruleno

        if all(slword != pattern_word for pattern_word in pattern):
            print('Source word "{}" not in pattern "{}"'.format(slword, ngram), file=sys.stderr);
            return None, lineno + 1, ruleno

    sllemma, sltags = get_lemma_and_tags(slword)
    tllemma, tltags = get_lemma_and_tags(tlword)
    # start rule
    out = '  <rule c="{} {}: 1" weight="{}">\n'.format(ruleno, lineno, weight)
    if ngram == '':
        # ngram is empty: substitute the slword for a pattern
        out += '    <match lemma="{}" tags="{}"><select lemma="{}" tags = "{}"/></match>\n'.format(sllemma, sltags, tllemma, tltags)
    else: 
        # ngram is ok
        for pword in pattern:
            # output each word in pattern
            plemma, ptags = get_lemma_and_tags(pword)
            out += '    <match '
            if plemma != '':
                out += 'lemma="{}" '.format(plemma)
            out += 'tags="{}"'.format(ptags)
            if pword == slword:
                # current word in pattern is slword: add <select> element
                out += '><select lemma="{}" tags="{}"/></match>\n'.format(tllemma, tltags)
            else:
                out += '/>\n'
    out += '  </rule>\n'
    return out, lineno + 1, ruleno + 1

def make_rules(pair_name, freq_lex_fname, yasmet_data, ngram_fname, all_lambdas_fname, min_ngrams):
    """
    Make files with weighted rules.
    """
    rules_all_fname = os.path.join(yasmet_data, 'rules-all.txt')
    ngrams_all_fname = os.path.join(yasmet_data, 'ngrams-all.txt')
    final_rules_fname = os.path.join(yasmet_data, '{}.ngrams-lm-{}.xml'.format(pair_name, min_ngrams))

    # Merge ngrams to lambdas
    ngram_dict = {}
    with open(ngram_fname, 'r', encoding='utf-8') as ngram_file:
        for line in ngram_file:
            line == line.strip()
            if line != '':
                parts = line.strip().split('\t') + ['']
                ngram_dict[int(parts[0])] = parts[1]

    sl_tl, sl_tl_defaults, index, rindex = read_freq_lex_file(freq_lex_fname)
    with open(all_lambdas_fname, 'r', encoding='utf-8') as lambda_file,\
         open(rules_all_fname, 'w', encoding='utf-8') as rule_file,\
         open(ngrams_all_fname, 'w', encoding='utf-8') as ngram_file,\
         open(final_rules_fname, 'w', encoding='utf-8') as final_file:
        lineno, ruleno = 1, 1
        final_file.write('<rules>\n')
        for line in lambda_file:
            if '@@@' not in line:
                slword, ngid, trad, lbda = line.strip().replace(':', ' ').split(' ')
                ngram = ngram_dict[int(ngid)]
                
                # Lambdas to rules (rules in tab-separated format with numbered ngrams)
                # This is a legacy intermediate step, which might not be really needed anymore
                rule_file.write('{}\t{}\t{}\t{}\n'.format(slword, lbda, trad, ngram))

                tlid = int(trad)
                if (slword, tlid) not in rindex:
                    print('({}, {}) not in index'.format(slword, tlid), file=sys.stderr)
                else:
                    tlword = rindex[(slword, tlid)]

                    # Lambdas to rules (rules in tab-separated format with explicit ngrams)
                    ngram_file.write('+ {}\t{}\t{}\t{}\t1\n'.format(lbda, slword, ngram, tlword))

                    # Rules to final xml
                    xml_rule, lineno, ruleno = make_xml_rule(lbda, slword, ngram, tlword, lineno, ruleno)
                    if xml_rule is not None:
                        final_file.write(xml_rule)
        final_file.write('</rules>')

def extract_maxent(pair_data, source, target, corpus_pair_name, corpus_name, data_folder, cand_fname, freq_lex_fname):
    """
    Run all stuff concerning maximum entropy learning.
    """
    pair = '{}-{}'.format(source, target)
    yasmet_data = 'yasmet.' + pair
    if not os.path.exists(yasmet_data):
        os.mkdir(yasmet_data)
    event_fname, ngram_fname = ngram_count_patterns_maxent(cand_fname, freq_lex_fname, yasmet_data)
    all_lambdas_fname, min_ngrams = get_lambdas(yasmet_data, event_fname)
    make_rules(corpus_pair_name, freq_lex_fname, yasmet_data, ngram_fname, all_lambdas_fname, min_ngrams)

if __name__ == "__main__":
    if not os.path.exists(data_folder):
        os.makedirs(data_folder)

    print('Preparing corpora')
    btime = clock()

    # tag corpora
    slinecount, sfname = tag_corpus(pair_data, source, target, 
                                    corpus_pair_name, corpus_folder,
                                    corpus_name, data_folder)
    tlinecount, tfname = tag_corpus(pair_data, target, source,
                                    corpus_pair_name, corpus_folder,
                                    corpus_name, data_folder)

    # clean tags (using moses script)
    sfname, tfname = clean_tags(corpus_pair_name, sfname, tfname, source, target, corpus_name, data_folder)

    # trim tags
    sfname = trim_tags(pair_data, source, target, lextools, sfname)
    tfname = trim_tags(pair_data, target, source, lextools, tfname)

    print('The corpora were prepared successfully in {:f}'.format(clock() - btime))

    print('Preparing data')
    btime = clock()
    prepare_data(pair_data, source, target, apertium_pair_name, data_folder)
    print('The data was prepared successfully in {:f}'.format(clock() - btime))

    print('Aligning corpus')
    btime = clock()
    cand_fname, freq_lex_fname = align_corpus(pair_data, source, target,
                                              corpus_pair_name, 
                                              corpus_name, data_folder)
    print('Corpus was aligned successfully in {:f}'.format(clock() - btime))

    print('Extracting rules')
    btime = clock()
    extract_maxent(pair_data, source, target, corpus_pair_name, corpus_name,
                   data_folder, cand_fname, freq_lex_fname)
    print('Rules were extracted successfully in {:f}'.format(clock() - btime))
