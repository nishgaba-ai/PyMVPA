#emacs: -*- mode: python-mode; py-indent-offset: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the PyMVPA package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Utility class to compute the transfer error of classifiers."""

__docformat__ = 'restructuredtext'

import copy

import numpy as N

from sets import Set
from StringIO import StringIO
from math import log10, ceil

from mvpa.misc.errorfx import MeanMismatchErrorFx
from mvpa.misc import warning
from mvpa.misc.state import StateVariable, Stateful
from mvpa.base.dochelpers import enhancedDocString

if __debug__:
    from mvpa.misc import debug


class ConfusionMatrix(object):
    """Simple class for confusion matrix computation / display.

    Implementation is aimed to be simple, thus it delays actual
    computation of confusion matrix untill all data is acquired (to
    figure out complete set of labels. If testing data doesn't have a
    complete set of labels, but you like to include all labels,
    provide them as a parameter to constructor.
    """


    _STATS_DESCRIPTION = (
        ('TP', 'true positive (AKA hit)', None),
        ('TN', 'true negative (AKA correct rejection)', None),
        ('FP', 'false positive (AKA false alarm, Type I error)', None),
        ('FN', 'false negative (AKA miss, Type II error)', None),
        ('TPR', 'true positive rate (AKA hit rate, recall, sensitivity)',
                'TPR = TP / P = TP / (TP + FN)'),
        ('FPR', 'false positive rate (AKA false alarm rate, fall-out)',
                'FPR = FP / N = FP / (FP + TN)'),
        ('ACC', 'accuracy', 'ACC = (TP + TN) / (P + N)'),
        ('SPC', 'specificity', 'SPC = TN / (FP + TN) = 1 - FPR'),
        ('PPV', 'positive predictive value (AKA precision)',
                'PPV = TP / (TP + FP)'),
        ('NPV', 'negative predictive value', 'NPV = TN / (TN + FN)'),
        ('FDR', 'false discovery rate', 'FDR = FP / (FP + TP)'),
        ('MCC', "Matthews Correlation Coefficient",
                "MCC = (TP*TN - FP*FN)/sqrt(P N P' N')"),
        )

    # XXX Michael: - How do multiple sets work and what are they there for?
    # YYY Yarik:   - Set is just a tuple (targets, predictions). While
    #                'computing' the matrix, all sets are considered together.
    def __init__(self, labels=None, targets=None, predictions=None):
        """Initialize ConfusionMatrix with optional list of `labels`

        :Parameters:
         labels : list
           Optional set of labels to include in the matrix
         targets
           Optional set of targets
         predictions
           Optional set of predictions
        """
        if labels == None:
            labels = []
        self.__labels = labels
        """List of known labels"""
        self.__computed = False
        """Flag either it was computed for a given set of data"""
        self.__sets = []
        """Datasets (target, prediction) to compute confusion matrix on"""
        self.__matrix = None
        """Resultant confusion matrix"""

        if not targets is None or not predictions is None:
            if not targets is None and not predictions is None:
                self.add(targets=targets, predictions=predictions)
            else:
                raise ValueError, \
                      "Please provide none or both targets and predictions"


    def add(self, targets, predictions):
        """Add new results to the set of known results"""
        if len(targets) != len(predictions):
            raise ValueError, \
                  "Targets[%d] and predictions[%d]" % (len(targets),
                                                       len(predictions)) + \
                  " have different number of samples"

        # enforce labels in predictions to be of the same datatype as in
        # targets, since otherwise we are getting doubles for unknown at a
        # given moment labels
        for i in xrange(len(targets)):
            t1, t2 = type(targets[i]), type(predictions[i])
            if t1 != t2:
                #warning("Obtained target %s and prediction %s are of " %
                #       (t1, t2) + "different datatypes.")
                if isinstance(predictions, tuple):
                    predictions = list(predictions)
                predictions[i] = t1(predictions[i])

        self.__sets.append( (targets, predictions) )
        self.__computed = False


    def _compute(self):
        """Actually compute the confusion matrix based on all the sets"""
        if self.__computed:
            return

        if __debug__:
            if not self.__matrix is None:
                debug("LAZY", "Have to recompute ConfusionMatrix %s" % `self`)

        # TODO: BinaryClassifier might spit out a list of predictions for each
        # value need to handle it... for now just keep original labels
        try:
            # figure out what labels we have
            labels = \
                list(reduce(lambda x, y: x.union(Set(y[0]).union(Set(y[1]))),
                            self.__sets,
                            Set(self.__labels)))
        except:
            labels = self.__labels

        labels.sort()
        self.__labels = labels          # store the recomputed labels

        Nlabels, Nsets = len(labels), len(self.__sets)

        if __debug__:
            debug("CM", "Got labels %s" % labels)

        # Create a matrix for all votes
        mat_all = N.zeros( (Nsets, Nlabels, Nlabels), dtype=int )

        # create total number of samples of each label counts
        # just for convinience I guess since it can always be
        # computed from mat_all
        counts_all = N.zeros( (Nsets, Nlabels) )

        # reverse mapping from label into index in the list of labels
        rev_map = dict([ (x[1], x[0]) for x in enumerate(labels)])
        for iset, (targets, predictions) in enumerate(self.__sets):
            for t,p in zip(targets, predictions):
                mat_all[iset, rev_map[p], rev_map[t]] += 1


        # for now simply compute a sum of votes across different sets
        # we might do something more sophisticated later on, and this setup
        # should easily allow it
        self.__matrix = N.sum(mat_all, axis=0)
        self.__Nsamples = N.sum(self.__matrix, axis=0)
        self.__Ncorrect = sum(N.diag(self.__matrix))

        TP = N.diag(self.__matrix)
        offdiag = self.__matrix - N.diag(TP)
        stats = {'TP' : TP,
                 'FP' : N.sum(offdiag, axis=1),
                 'FN' : N.sum(offdiag, axis=0)}

        stats['CORR']  = N.sum(TP)
        stats['TN']  = stats['CORR'] - stats['TP']
        stats['P']  = stats['TP'] + stats['FN']
        stats['N']  = N.sum(stats['P']) - stats['P']
        stats["P'"] = stats['TP'] + stats['FP']
        stats["N'"] = stats['TN'] + stats['FN']
        stats['TPR'] = stats['TP'] / (1.0*stats['P'])
        stats['PPV'] = stats['TP'] / (1.0*stats["P'"])
        stats['NPV'] = stats['TN'] / (1.0*stats["N'"])
        stats['FDR'] = stats['FP'] / (1.0*stats["P'"])
        stats['SPC'] = (stats['TN']) / (1.0*stats['FP'] + stats['TN'])
        stats['MCC'] = \
            (stats['TP'] * stats['TN'] - stats['FP'] * stats['FN']) \
            / N.sqrt(1.0*stats['P']*stats['N']*stats["P'"]*stats["N'"])

        stats['ACC'] = N.sum(TP)/(1.0*N.sum(stats['P']))
        stats['ACC%'] = stats['ACC'] * 100.0

        self.__stats = stats
        self.__computed = True


    def __str__(self, header=True, percents=True, summary=True,
                print_empty=False, description=True):
        """'Pretty print' the matrix"""
        self._compute()

        # some shortcuts
        labels = self.__labels
        matrix = self.__matrix

        out = StringIO()
        # numbers of different entries
        Nlabels = len(labels)
        Nsamples = self.__Nsamples.astype(int)

        if len(self.__sets) == 0:
            return "Empty confusion matrix"

        Ndigitsmax = int(ceil(log10(max(Nsamples))))
        Nlabelsmax = max( [len(str(x)) for x in labels] )

        # length of a single label/value
        L = max(Ndigitsmax+2, Nlabelsmax) #, len("100.00%"))
        res = ""

        stats_perpredict = ["P'", "N'", 'FP', 'FN', 'PPV', 'NPV', 'TPR',
                            'SPC', 'FDR', 'MCC']
        stats_pertarget = ['P', 'N', 'TP', 'TN']
        stats_summary = ['ACC', 'ACC%']


        #prefixlen = Nlabelsmax + 2 + Ndigitsmax + 1
        prefixlen = Nlabelsmax + 1
        pref = ' '*(prefixlen) # empty prefix

        if matrix.shape != (Nlabels, Nlabels):
            raise ValueError, \
                  "Number of labels %d doesn't correspond the size" + \
                  " of a confusion matrix %s" % (Nlabels, matrix.shape)

        # list of lists of what is printed
        printed = []
        underscores = [" %s" % ("-" * L)] * Nlabels
        if header:
            # labels
            printed.append(['----------.        '])
            printed.append(['predictions\\targets'] + labels)
            # underscores
            printed.append(['            `------'] \
                           + underscores + stats_perpredict)

        # matrix itself
        for i, line in enumerate(matrix):
            printed.append(
                [labels[i]] +
                [ str(x) for x in line ] +
                [ '%.2g' % self.__stats[x][i] for x in stats_perpredict])

        if summary:
            printed.append(['Per target:'] + underscores)
            for stat in stats_pertarget:
                printed.append([stat] + ['%.2g' \
                    % self.__stats[stat][i] for i in xrange(Nlabels)])

            printed.append(['SUMMARY:'] + underscores)

            for stat in stats_summary:
                printed.append([stat] + ['%.2g' % self.__stats[stat]])

        # equalize number of elements in each row
        Nelements_max = max(len(x) for x in printed)
        for i,printed_ in enumerate(printed):
            printed[i] += [''] * (Nelements_max - len(printed_))

        # figure out lengths within each column
        aprinted = N.asarray(printed)
        col_width = [ max( [len(x) for x in column] ) for column in aprinted.T ]

        for i, printed_ in enumerate(printed):
            for j, item in enumerate(printed_):
                item = str(item)
                NspacesL = ceil((col_width[j] - len(item))/2.0)
                NspacesR = col_width[j] - NspacesL - len(item)
                out.write("%%%ds%%s%%%ds " \
                          % (NspacesL, NspacesR) % ('', item, ''))
            out.write("\n")


        if description:
            out.write("\nStatistics computed in 1-vs-rest fashion per each " \
                      "target.\n")
            out.write("Abbreviations (for details see " \
                      "http://en.wikipedia.org/wiki/ROC_curve):\n")
            for d, val, eq in self._STATS_DESCRIPTION:
                out.write(" %-3s: %s\n" % (d, val))
                if eq is not None:
                    out.write("      " + eq + "\n")

        #out.write("%s" % printed)
        result = out.getvalue()
        out.close()
        return result


    def __iadd__(self, other):
        """Add the sets from `other` s `ConfusionMatrix` to current one
        """
        #print "adding ", other, " to ", self
        # need to do shallow copy, or otherwise smth like "cm += cm"
        # would loop forever and exhaust memory eventually
        othersets = copy.copy(other.__sets)
        for set in othersets:
            self.add(set[0], set[1])
        return self


    def __add__(self, other):
        """Add two `ConfusionMatrix`
        """
        result = copy.copy(self)
        result += other
        return result


    @property
    def matrices(self):
        """Return a list of separate confusion matrix per each stored set"""
        return [ self.__class__(labels=self.labels,
                                targets=x[0],
                                predictions=x[1]) for x in self.__sets]


    @property
    def labels(self):
        self._compute()
        return self.__labels


    @property
    def matrix(self):
        self._compute()
        return self.__matrix


    @property
    def percentCorrect(self):
        self._compute()
        return 100.0*self.__Ncorrect/sum(self.__Nsamples)


    @property
    def error(self):
        self._compute()
        return 1.0-self.__Ncorrect*1.0/sum(self.__Nsamples)

    sets = property(lambda self:self.__sets)



class ClassifierError(Stateful):
    """Compute (or return) some error of a (trained) classifier on a dataset.
    """

    confusion = StateVariable(enabled=False)
    """TODO Think that labels might be also symbolic thus can't directly
       be indicies of the array
    """

    training_confusion = StateVariable(enabled=False)
    """Proxy training_confusion from underlying classifier
    """

    def __init__(self, clf, labels=None, train=True, **kwargs):
        """Initialization.

        :Parameters:
          clf : Classifier
            Either trained or untrained classifier
          labels : list
            if provided, should be a set of labels to add on top of the
            ones present in testdata
          train : bool
            unless train=False, classifier gets trained if
            trainingdata provided to __call__
        """
        Stateful.__init__(self, **kwargs)
        self.__clf = clf

        self._labels = labels
        """Labels to add on top to existing in testing data"""

        self.__train = train
        """Either to train classifier if trainingdata is provided"""


    __doc__ = enhancedDocString('ClassifierError', locals(), Stateful)


    def __copy__(self):
        """TODO: think... may be we need to copy self.clf"""
        out = ClassifierError.__new__(TransferError)
        ClassifierError.__init__(out, self.clf)
        return out


    def _precall(self, testdataset, trainingdataset=None):
        """Generic part which trains the classifier if necessary
        """
        if not trainingdataset is None:
            if self.__train:
                # XXX can be pretty annoying if triggered inside an algorithm
                # where it cannot be switched of, but retraining might be
                # intended or at least not avoidable.
                # Additonally isTrained docs say:
                #   MUST BE USED WITH CARE IF EVER
                #
                # switching it off for now
                #if self.__clf.isTrained(trainingdataset):
                #    warning('It seems that classifier %s was already trained' %
                #            self.__clf + ' on dataset %s. Please inspect' \
                #                % trainingdataset)
                if self.states.isEnabled('training_confusion'):
                    self.__clf.states._changeTemporarily(enable_states=['training_confusion'])
                self.__clf.train(trainingdataset)
                if self.states.isEnabled('training_confusion'):
                    self.training_confusion = self.__clf.training_confusion
                    self.__clf.states._resetEnabledTemporarily()

        if self.__clf.states.isEnabled('trained_labels') and \
               not testdataset is None:
            newlabels = Set(testdataset.uniquelabels) - self.__clf.trained_labels
            if len(newlabels)>0:
                warning("Classifier %s wasn't trained to classify labels %s" %
                        (`self.__clf`, `newlabels`) +
                        " present in testing dataset. Make sure that you has" +
                        " not mixed order/names of the arguments anywhere")

        ### Here checking for if it was trained... might be a cause of trouble
        # XXX disabled since it is unreliable.. just rely on explicit
        # self.__train
        #    if  not self.__clf.isTrained(trainingdataset):
        #        self.__clf.train(trainingdataset)
        #    elif __debug__:
        #        debug('CERR',
        #              'Not training classifier %s since it was ' % `self.__clf`
        #              + ' already trained on dataset %s' % `trainingdataset`)


    def _call(self, testdataset, trainingdataset=None):
        raise NotImplementedError


    def _postcall(self, testdataset, trainingdataset=None, error=None):
        pass


    def __call__(self, testdataset, trainingdataset=None):
        """Compute the transfer error for a certain test dataset.

        If `trainingdataset` is not `None` the classifier is trained using the
        provided dataset before computing the transfer error. Otherwise the
        classifier is used in it's current state to make the predictions on
        the test dataset.

        Returns a scalar value of the transfer error.
        """
        self._precall(testdataset, trainingdataset)
        error = self._call(testdataset, trainingdataset)
        self._postcall(testdataset, trainingdataset, error)
        return error


    @property
    def clf(self):
        return self.__clf


    @property
    def labels(self):
        return self._labels



class TransferError(ClassifierError):
    """Compute the transfer error of a (trained) classifier on a dataset.

    The actual error value is computed using a customizable error function.
    Optionally the classifier can be trained by passing an additional
    training dataset to the __call__() method.
    """

    null_prob = StateVariable(enabled=True)
    """Stores the probability of an error result under the NULL hypothesis"""

    def __init__(self, clf, errorfx=MeanMismatchErrorFx(), labels=None,
                 null_dist=None, **kwargs):
        """Initialization.

        :Parameters:
          clf : Classifier
            Either trained or untrained classifier
          errorfx
            Functor that computes a scalar error value from the vectors of
            desired and predicted values (e.g. subclass of `ErrorFunction`)
          labels : list
            if provided, should be a set of labels to add on top of the
            ones present in testdata
          null_dist : instance of distribution estimator
        """
        ClassifierError.__init__(self, clf, labels, **kwargs)
        self.__errorfx = errorfx
        self.__null_dist = null_dist


    __doc__ = enhancedDocString('TransferError', locals(), ClassifierError)


    def __copy__(self):
        """TODO: think... may be we need to copy self.clf"""
        # TODO TODO -- use ClassifierError.__copy__
        out = TransferError.__new__(TransferError)
        TransferError.__init__(out, self.clf, self.errorfx, self._labels)

        return out


    def _call(self, testdataset, trainingdataset=None):
        """Compute the transfer error for a certain test dataset.

        If `trainingdataset` is not `None` the classifier is trained using the
        provided dataset before computing the transfer error. Otherwise the
        classifier is used in it's current state to make the predictions on
        the test dataset.

        Returns a scalar value of the transfer error.
        """

        predictions = self.clf.predict(testdataset.samples)

        # compute confusion matrix
        # XXX should migrate into ClassifierError.__postcall?
        # YYY probably not because other childs could estimate it
        #  not from test/train datasets explicitely, see
        #  `ConfusionBasedError`, where confusion is simply
        #  bound to classifiers confusion matrix
        if self.states.isEnabled('confusion'):
            self.confusion = ConfusionMatrix(
                labels=self.labels, targets=testdataset.labels,
                predictions=predictions)

        # compute error from desired and predicted values
        error = self.__errorfx(predictions,
                               testdataset.labels)

        return error


    def _postcall(self, vdata, wdata=None, error=None):
        """
        """
        # estimate the NULL distribution when functor and training data is
        # given
        if not self.__null_dist is None and not wdata is None:
            # we need a matching transfer error instances (e.g. same error
            # function), but we have to disable the estimation of the null
            # distribution in that child to prevent infinite looping.
            null_terr = copy.copy(self)
            null_terr.__null_dist = None
            self.__null_dist.fit(null_terr, wdata, vdata)


        # get probability of error under NULL hypothesis if available
        if not error is None and not self.__null_dist is None:
            self.null_prob = self.__null_dist.cdf(error)


    @property
    def errorfx(self): return self.__errorfx



class ConfusionBasedError(ClassifierError):
    """For a given classifier report an error based on internally
    computed error measure (given by some `ConfusionMatrix` stored in
    some state variable of `Classifier`).

    This way we can perform feature selection taking as the error
    criterion either learning error, or transfer to splits error in
    the case of SplitClassifier
    """

    def __init__(self, clf, labels=None, confusion_state="training_confusion",
                 **kwargs):
        """Initialization.

        :Parameters:
          clf : Classifier
            Either trained or untrained classifier
          confusion_state
            Id of the state variable which stores `ConfusionMatrix`
          labels : list
            if provided, should be a set of labels to add on top of the
            ones present in testdata
        """
        ClassifierError.__init__(self, clf, labels, **kwargs)

        self.__confusion_state = confusion_state
        """What state to extract from"""

        if not clf.states.isKnown(confusion_state):
            raise ValueError, \
                  "State variable %s is not defined for classifier %s" % \
                  (confusion_state, `clf`)
        if not clf.states.isEnabled(confusion_state):
            if __debug__:
                debug('CERR', "Forcing state %s to be enabled for %s" %
                      (confusion_state, `clf`))
            clf.states.enable(confusion_state)


    __doc__ = enhancedDocString('ConfusionBasedError', locals(),
                                ClassifierError)


    def _call(self, testdata, trainingdata=None):
        """Extract transfer error. Nor testdata, neither trainingdata is used
        """
        confusion = self.clf.states.getvalue(self.__confusion_state)
        self.confusion = confusion
        return confusion.error
