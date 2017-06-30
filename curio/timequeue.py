# timequeue.py
#
# This is a work in progress.  Something a bit experimental.
# Not used in Curio proper right now.

import heapq
from math import log2

class TimeQueue:
    def __init__(self, base=0.0):
        self.near_deadline = base
        self.near = []

        # Set of buckets for timeouts occurring 4, 16, 64s in the future (from deadline)
        self.far = [ set() for _ in range(8) ]
        self.far_deadlines = [self.near_deadline] + [self.near_deadline + 4 ** n for n in range(1,8) ]

    def _advance(self, deadline):
        # Sets a new near deadline and adjusts the buckets if necessary
        self.near_deadline = deadline

        # Scan through the buckets and replace items as necessary.  
        # There are two rules:
        #
        # 1. Any bucket with a deadline < near_deadline is rehashed
        # 2. If a bucket overtakes the next bucket, it is rehashed.

        bucketno = 0
        bucket_deadline = deadline
        while bucketno < 8:
            # If a bucket has a deadline less than the new deadline.
            # Its contents need to be processed.  Some of its items
            # might need to go into the near queue.

            if self.far_deadlines[bucketno] < bucket_deadline:
                self.far_deadlines[bucketno] = bucket_deadline
                bucket = self.far[bucketno]
                if bucket:
                    self.far[bucketno] = set()
                    for expires, item in bucket:
                        self.push(item, expires)
                bucketno += 1

                # If the next bucket has a deadline that's greater than
                # than the deadline of the current bucket, we're done.
                # Otherwise, we move on to reprocess its contents as well.
                if bucketno < 8 and self.far_deadlines[bucketno] > bucket_deadline:
                    break
                bucket_deadline = deadline + 4**bucketno
            else:
                break

    def next_deadline(self, max_deadline):
        '''
        Return the next deadline stored up to max_deadline. If there are
        no deadlines stored, max_deadline is returned
        '''
        if not self.near:
            # If nothing is stored in the near queue. We'll advance the deadline
            self._advance(max_deadline)

        if self.near and self.near[0][0] < max_deadline:
            return self.near[0][0]
        else:
            return max_deadline

    def push(self, item, expires):
        '''
        Push a new item onto the time queue.
        '''
        # If the expiration time is closer than the current near deadline,
        # it gets pushed onto a heap in order to preserve order
    
        qitem = (expires, item)

        if expires < self.near_deadline:
            heapq.heappush(self.near, qitem)


        # Otherwise, the item gets dropped into a bucket for future processing
        else:
            delta = expires - self.near_deadline
            bucketno = 0 if delta < 4.0 else int(0.5*log2(delta))
            if bucketno > 7:
                bucketno = 7
            self.far[bucketno].add(qitem)

        return qitem

    def expired(self, deadline):
        '''
        An iterator that returns all items that have expired up to max_deadline
        '''
        if deadline >= self.near_deadline:
            self._advance(deadline)
            
        near = self.near
        while near and near[0][0] < deadline:
            yield heapq.heappop(near)

    def cancel(self, qitem):
        '''
        Cancel a prior timeout. qitem is a prior item returned by push()
        '''
        expires, item = qitem

        # If the expiration time is beyond the current near deadline, we
        # remove the item from the queue.   If not, we leave it in place.
        delta = expires - self.near_deadline
        if delta >= 0:
            bucketno = 0 if delta < 4.0 else int(0.5*log2(delta))
            if bucketno > 7:
                bucketno = 7
            while self.far_deadlines[bucketno] <= expires and bucketno < 8:
                self.far[bucketno].discard(qitem)
                bucketno += 1
