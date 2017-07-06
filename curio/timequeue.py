# timequeue.py
#
# A Discussion About Time.
# 
# Internally, Curio must manage time for two different reasons,
# sleeping and for timeouts.  Aside from toy examples, most people
# aren't going to write that code sits around sleeping. Instead,
# the more common use is timeouts.  Timeouts are kind of 
# interesting though--when a timeout is set, there is a general
# expectation that it will probably NOT fire.  The firing of a timeout
# is an exceptional event. Most of the time, a timeout will be
# cancelled before it is allowed to expire.
#
# This presents an interesting implementation challenge for managing
# time.  It is most common to see time managed by sorting different
# expiration times in some way. For example, placing them in a sorted
# list, or ordering them on a heap in a priority queue.  Although
# operations on these structures can often be managed in O(log N) time,
# they might not be necessary at all if you make some different
# assumptions about time management.
# 
# The queue implementation here is based on the idea that expiration
# times in the distant future don't really need to be precisely
# sorted.  Instead, you can merely drop expiration times into
# different buckets, representing different time periods in the
# future.  If later cancelled, you can delete the time from a bucket.
# This can all be managed using simple dictionaries.  Thus,
# manipulating the buckets is O(1)--meaning it can be extremely cheap
# to setup and teardown a timeout that never happens.  For expiration
# times that aren't cancelled, they slowly cascade forward, eventually
# becoming sorted as the deadline approaches.  Probably the closest
# similar thing might the implementation of Timing Wheels (e.g., as
# used in the Linux kernel).
#
# One unusual aspect to the implementation is that to better manage
# timeouts, it's better to allow time to more slowly creep along in an
# incremental manner than to make large jumps.  For example, suppose a
# collection of tasks have all set timeouts 5 minutes into the future.
# When polling for I/O, you might be inclined to find the nearest
# deadline and pass that to select() (something close to 5 minutes).
# The only problem with this approach is that you'll have to sort all
# of the deadlines to figure it out (which kind of defeats the
# purpose).  Instead of doing that, it's better to operate with a more
# narrow window.  For example, are there any deadlines that expire in
# the next second?  If so, go ahead and use them.  Otherwise, just 
# put a one-second timeout on select(). 

import heapq
from math import log2

class TimeQueue:
    def __init__(self, timeslice=1.0):
        self.near_deadline = 0.0
        self.timeslice = timeslice
        self.near = []

        # Set of buckets for timeouts occurring 4, 16, 64s, 256s, etc. in the future (from deadline)
        self.far = [ {} for _ in range(8) ]
        self.far_deadlines = [self.near_deadline] + [self.near_deadline + 4 ** n for n in range(1,8) ]

    def _advance(self, deadline):
        # Sets a new near deadline and adjusts the buckets if necessary
        if deadline - self.near_deadline >= self.timeslice:
            self.near_deadline = deadline
        else:
            self.near_deadline += self.timeslice

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
                    self.far[bucketno] = {}
                    for item, expires in bucket.items():
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

    def next_deadline(self, current_clock):
        '''
        Returns the number of seconds to delay.  current_clock is the
        current clock value.
        '''
        max_deadline = current_clock + self.timeslice
        if not self.near:
            # If nothing is stored in the near queue. We'll advance the deadline
            # to the new deadline
            self._advance(max_deadline)

        if self.near and self.near[0][0] < max_deadline:
            delta = self.near[0][0] - current_clock
            return delta if delta > 0 else 0
        else:
            return self.timeslice

    def push(self, item, expires):
        '''
        Push a new item onto the time queue.
        '''
        if expires is None:
            return

        # If the expiration time is closer than the current near deadline,
        # it gets pushed onto a heap in order to preserve order
        if expires < self.near_deadline:
            heapq.heappush(self.near, (expires, item))


        # Otherwise, the item gets dropped into a bucket for future processing
        else:
            delta = expires - self.near_deadline
            bucketno = 0 if delta < 4.0 else int(0.5*log2(delta))
            if bucketno > 7:
                bucketno = 7
            self.far[bucketno][item] = expires

    def expired(self, deadline):
        '''
        An iterator that returns all items that have expired up to deadline
        '''
        if deadline >= self.near_deadline:
            self._advance(deadline)
            
        near = self.near
        while near and near[0][0] < deadline:
            yield heapq.heappop(near)

    def cancel(self, item, expires):
        '''
        Cancel a prior timeout. The combination of (item,expires)
        should match a prior push() operation.
        '''
        # If the expiration time is beyond the current near deadline, we
        # remove the item from the queue.   If not, we leave it in place.
        if expires is None:
            return
        delta = expires - self.near_deadline
        if delta >= 0:
            bucketno = 0 if delta < 4.0 else int(0.5*log2(delta))
            if bucketno > 7:
                bucketno = 7
            while self.far_deadlines[bucketno] <= expires and bucketno < 8:
                self.far[bucketno].pop(item, None)
                bucketno += 1
