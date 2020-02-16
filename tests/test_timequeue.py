
from curio.timequeue import TimeQueue

def test_timequeue_expired():
    q = TimeQueue()
    
    delta = q.next_deadline(10)
    assert delta == None

    q.push('a', 50)
    q.push('b', 25)
    q.push('c', 100)
    # this should return the number of seconds to the next deadline
    delta = q.next_deadline(5)
    assert delta == 20
    items = list(q.expired(25))
    assert items == [(25, 'b')]

    items = list(q.expired(101))
    assert items == [(50, 'a'), (100, 'c')]

